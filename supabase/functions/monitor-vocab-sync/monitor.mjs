const APP_URL = 'https://lesong36.github.io/vocab-master/vocabulary_app.html';
const labels = {
  invalid_payload: '学习档案包含数据库不接受的数据',
  receipt_invalid: '云端保存回执不完整',
  database_rejected: '数据库拒绝保存学习档案',
  storage_failed: '浏览器本机保存失败',
  sync_failed: '同步持续失败',
  pending_backlog: '答题记录等待云端确认超过 10 分钟',
  journal_mismatch: '云端档案与独立答题日志不一致',
};

export const buildAlertEmail = row => {
  const test = row.kind === 'test';
  const recovered = row.kind === 'recovered';
  const subject = test ? '【测试】单词学习保存异常邮件预警已接通'
    : recovered ? '【已恢复】单词学习记录同步'
    : '【保存异常】单词学习记录需要检查';
  const started = new Date(row.started_at).toISOString();
  const pending = Number.isSafeInteger(Number(row.pending_count)) ? Math.max(0, Number(row.pending_count)) : 0;
  const reason = labels[row.error_code] || '学习记录保存异常';
  const text = test
    ? '这是一封邮件预警链路测试，未修改任何学习记录。\n严重保存错误、持续同步失败或待同步记录积压时，会通过此邮箱通知。'
    : recovered ? `这项学习记录保存异常已消除：${reason}。其他设备或故障的状态请查看应用。`
    : `检测到：${reason}。\n首次发现时间（UTC）：${started}\n已上报的待确认答题数量：${pending}\n这是保存异常预警，不代表记录已丢失。请打开应用查看同步状态，保留本机记录并导出备份，避免清除浏览器缓存。`;
  return { subject, text: `${text}\n\n查看应用：${APP_URL}` };
};

export function createMonitorHandler({ env, fetch: fetcher }) {
  const rpc = async (name, body = {}) => {
    const response = await fetcher(`${env('SUPABASE_URL')}/rest/v1/rpc/${name}`, {
      method: 'POST', signal: AbortSignal.timeout(10000),
      headers: { 'Content-Type': 'application/json', apikey: env('SUPABASE_SERVICE_ROLE_KEY'), Authorization: `Bearer ${env('SUPABASE_SERVICE_ROLE_KEY')}` },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`rpc_${response.status}`);
    return response.status === 204 ? null : response.json();
  };
  return async request => {
    const secret = env('DAILY_REPORT_CRON_SECRET');
    if (request.method !== 'POST' || !secret || request.headers.get('x-daily-report-secret') !== secret) {
      return new Response('Unauthorized', { status: 401 });
    }
    if (!env('SUPABASE_URL') || !env('SUPABASE_SERVICE_ROLE_KEY') || !env('RESEND_API_KEY') || !env('DAILY_REPORT_FROM')) {
      return Response.json({ error: 'alert_configuration_missing' }, { status: 503 });
    }
    let sent = 0, failed = 0;
    try {
      await rpc('collect_vocab_sync_alerts_v1');
      const deliveries = await rpc('claim_vocab_sync_alerts_v1');
      for (const row of deliveries || []) {
        let providerId = null, failureCode = null;
        try {
          const auth = await fetcher(`${env('SUPABASE_URL')}/auth/v1/admin/users/${encodeURIComponent(row.user_id)}`, {
            signal: AbortSignal.timeout(10000),
            headers: { apikey: env('SUPABASE_SERVICE_ROLE_KEY'), Authorization: `Bearer ${env('SUPABASE_SERVICE_ROLE_KEY')}` },
          });
          if (!auth.ok) throw new Error(`recipient_lookup_${auth.status}`);
          const user = await auth.json();
          if (!user.email || !user.email_confirmed_at) throw new Error('recipient_unverified');
          const email = buildAlertEmail(row);
          const response = await fetcher('https://api.resend.com/emails', {
            method: 'POST', signal: AbortSignal.timeout(10000),
            headers: { Authorization: `Bearer ${env('RESEND_API_KEY')}`, 'Content-Type': 'application/json', 'Idempotency-Key': `vocab-sync-alert/${row.id}` },
            body: JSON.stringify({ from: env('DAILY_REPORT_FROM'), to: [user.email], ...email }),
          });
          if (!response.ok) throw new Error(`mail_provider_${response.status}`);
          const result = await response.json();
          if (typeof result.id !== 'string' || !result.id) throw new Error('mail_receipt_invalid');
          providerId = result.id;
        } catch (error) {
          // Never store provider bodies, user data or tokens in the delivery audit.
          failureCode = /^(recipient_lookup_\d+|recipient_unverified|mail_provider_\d+|mail_receipt_invalid)$/.test(error.message)
            ? error.message : 'mail_transport_failed';
        }
        await rpc('finish_vocab_sync_alert_v1', {
          p_delivery_id: row.id, p_lease_token: row.lease_token,
          p_provider_id: providerId, p_failure_code: failureCode,
        });
        if (providerId) sent++; else failed++;
      }
      return Response.json({ sent, failed }, { status: failed ? 502 : 200 });
    } catch {
      // A failed audit write leaves a reclaimable lease; it must not claim mail success.
      return Response.json({ error: 'alert_monitor_failed', sent, failed }, { status: 503 });
    }
  };
}
