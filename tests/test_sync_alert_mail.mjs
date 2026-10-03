import assert from 'node:assert/strict';
import { createMonitorHandler, buildAlertEmail } from '../supabase/functions/monitor-vocab-sync/monitor.mjs';

const settings = { SUPABASE_URL: 'https://test.invalid', SUPABASE_SERVICE_ROLE_KEY: 'server-only', RESEND_API_KEY: 'mail-only', DAILY_REPORT_FROM: 'test@example.invalid', DAILY_REPORT_CRON_SECRET: 'scheduler-only' };
const row = { id: 'delivery-1', lease_token: 'lease-1', user_id: 'user-1', kind: 'alert', error_code: 'database_rejected', pending_count: 3, started_at: '2026-10-03T00:00:00Z' };
const request = () => new Request('https://test.invalid', { method: 'POST', headers: { 'x-daily-report-secret': 'scheduler-only' } });
for (const mode of ['success', 'rejected', 'transport', 'finish_failed']) {
  const calls = [];
  const fetcher = async (url, options) => {
    const body = options.body ? JSON.parse(options.body) : null;
    calls.push({ url, options, body });
    if (url.includes('collect_')) return Response.json(0);
    if (url.includes('claim_')) return Response.json([row]);
    if (url.includes('/admin/users/')) return Response.json({ email: 'learner@example.invalid', email_confirmed_at: row.started_at });
    if (url === 'https://api.resend.com/emails') {
      assert.equal(options.headers['Idempotency-Key'], 'vocab-sync-alert/delivery-1');
      assert.deepEqual(body.to, ['learner@example.invalid']);
      assert(!JSON.stringify(body).includes('server-only'));
      if (mode === 'transport') throw new Error('secret raw details');
      return mode === 'rejected' ? Response.json({ error: 'private provider body' }, { status: 429 }) : Response.json({ id: 'provider-1' });
    }
    if (url.includes('finish_')) return mode === 'finish_failed' ? new Response('', { status: 500 }) : Response.json(true);
    throw Error('Unexpected request');
  };
  const response = await createMonitorHandler({ env: n => settings[n], fetch: fetcher })(request());
  assert.equal(response.status, mode === 'success' ? 200 : mode === 'finish_failed' ? 503 : 502);
  const finish = calls.find(c => c.url.includes('finish_')).body;
  assert.equal(finish.p_provider_id, ['success', 'finish_failed'].includes(mode) ? 'provider-1' : null);
  assert.equal(finish.p_failure_code, mode === 'rejected' ? 'mail_provider_429' : mode === 'transport' ? 'mail_transport_failed' : null);
}
let called = false;
const handler = createMonitorHandler({ env: n => settings[n], fetch: () => { called = true; } });
assert.equal((await handler(new Request('https://test.invalid'))).status, 401);
assert.equal(called, false);
assert.equal((await createMonitorHandler({ env: () => undefined, fetch: () => { called = true; } })(request())).status, 401);
assert.equal((await createMonitorHandler({ env: n => n === 'RESEND_API_KEY' ? undefined : settings[n], fetch: () => { called = true; } })(request())).status, 503);
assert.equal(called, false);
let mailSent = false, recordedFailure;
const unverified = createMonitorHandler({ env: n => settings[n], fetch: async (url, options) => {
  if (url.includes('collect_')) return Response.json(0);
  if (url.includes('claim_')) return Response.json([row]);
  if (url.includes('/admin/users/')) return Response.json({ email: 'unverified@example.invalid' });
  if (url.includes('finish_')) { recordedFailure = JSON.parse(options.body); return Response.json(true); }
  mailSent = true;
  throw new Error('Unverified recipient must not reach sender');
} });
assert.equal((await unverified(request())).status, 502);
assert.equal(mailSent, false);
assert.equal(recordedFailure.p_failure_code, 'recipient_unverified');
assert(buildAlertEmail({ ...row, kind: 'test' }).subject.includes('测试'));
assert(buildAlertEmail({ ...row, kind: 'recovered' }).subject.includes('已恢复'));
console.log('PASS: scheduler authentication, verified recipient, mail failures, durable completion, stable idempotency and labelled test/recovery messages');
