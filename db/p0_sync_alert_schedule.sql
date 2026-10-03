-- Deploy monitor-vocab-sync before scheduling. Reuse existing server-only Vault secrets.
-- No API keys or SMTP credentials belong in this file or the client application.
select cron.schedule(
  'monitor-vocabulary-learning-save',
  '*/5 * * * *',
  $job$
  select net.http_post(
    url := (select decrypted_secret from vault.decrypted_secrets where name = 'daily_report_project_url') || '/functions/v1/monitor-vocab-sync',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-daily-report-secret', (select decrypted_secret from vault.decrypted_secrets where name = 'daily_report_cron_secret')
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 120000
  );
  $job$
);
