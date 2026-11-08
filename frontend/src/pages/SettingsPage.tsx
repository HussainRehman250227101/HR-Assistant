import { useAgentConfig, useAutoScoring, useLLMStatus } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Badge, Card, ErrorAlert, KeyValue, Loading, PageHeader } from '../components/ui'
import { formatDate } from '../lib/format'

const interval = (seconds: number) => (seconds % 60 === 0 ? `${seconds / 60} minute${seconds === 60 ? '' : 's'}` : `${seconds} seconds`)

const yes = (v: unknown) => <Badge value={v ? 'COMPLETED' : 'FAILED'} label={v ? 'Configured' : 'Missing'} />
const optional = (v: unknown) => <Badge value={v ? 'COMPLETED' : undefined} label={v ? 'Configured' : 'Not set (optional)'} />

export function SettingsPage() {
  const { isAdmin } = useAuth()
  const config = useAgentConfig()
  const llm = useLLMStatus(isAdmin)
  const auto = useAutoScoring()
  const i = config.data?.integration
  const telephony = config.data?.voice_mode === 'telephony'
  const twilioBadge = telephony ? yes : optional
  return (
    <>
      <PageHeader title="Integrations" subtitle="Server-side configuration status. Secrets are never sent to the browser — only whether each one is set." />
      <div className="space-y-6">
        <Card title="Automatic resume scoring — Celery">
          {auto.isLoading ? <Loading /> : auto.data ? (
            <KeyValue items={[
              ['Status', <Badge key="s" value={auto.data.enabled ? 'COMPLETED' : undefined} label={auto.data.enabled ? 'Enabled' : 'Disabled'} />],
              ['Checks for new resumes every', interval(auto.data.interval_seconds)],
              ['Max resumes scored per check', String(auto.data.batch_limit)],
              ['Resumes waiting to be scored', String(auto.data.awaiting_scoring)],
              ['Last automatic scoring run', auto.data.last_automatic_run_at ? formatDate(auto.data.last_automatic_run_at) : 'None yet'],
            ]} />
          ) : <ErrorAlert error={auto.error} />}
          <p className="mt-4 text-xs text-slate-500">
            Runs only while the worker and the scheduler are running (from <code>backend/</code>): <code>celery -A config worker --pool=solo --loglevel=info</code> and <code>celery -A config beat --loglevel=info</code>. Each resume is scored automatically once; a failed run needs <em>Score resume</em> on the candidate. Scores always wait for a recruiter's shortlist decision.
          </p>
        </Card>
        <ErrorAlert error={config.error} />
        {config.isLoading ? <Loading /> : i && (
          <>
            <Card title="AI voice screening — ElevenLabs">
              <KeyValue items={[
                ['Screening voice mode', telephony ? 'Telephony (Twilio phone calls)' : 'Browser (WebRTC session in the HR app, no phone call)'],
                ['Browser voice sessions', <Badge key="b" value={i.browser_voice_ready ? 'COMPLETED' : 'FAILED'} label={i.browser_voice_ready ? 'Ready' : 'Not configured'} />],
                ['ElevenLabs API key', yes(i.elevenlabs_api_key)], ['ElevenLabs agent ID', yes(i.elevenlabs_agent_id)],
                ['Max sessions / attempts per screening', String(config.data?.browser_policy.max_attempts)],
                ['Unconnected session released after', `${config.data?.browser_policy.session_timeout_minutes} minutes`],
                ['Approved script', config.data?.script_version],
              ]} />
              <p className="mt-4 text-xs text-slate-500">
                Browser mode needs only the API key and the agent ID. The agent must have authentication enabled; the server mints a short-lived WebRTC token per session, so the API key and agent ID never reach the browser.
              </p>
            </Card>
            <Card title={telephony ? 'Telephony — Twilio + ElevenLabs (enabled)' : 'Telephony — Twilio + ElevenLabs (optional, disabled)'}>
              <KeyValue items={[
                ['Telephony provider', String(i.telephony_provider)], ['Voice AI provider', String(i.voice_ai_provider)],
                ['ElevenLabs phone-number ID (imported Twilio number)', twilioBadge(i.elevenlabs_agent_phone_number_id)],
                ['Webhook secret', twilioBadge(i.elevenlabs_webhook_secret)], ['Twilio account SID', twilioBadge(i.twilio_account_sid)],
                ['Twilio auth token', twilioBadge(i.twilio_auth_token)], ['Twilio phone number', twilioBadge(i.twilio_phone_number)],
                ['Allowed destinations', (i.allowed_dial_prefixes as string[]).join(', ')],
                ['Max attempts', String(config.data?.calling_policy.max_attempts)],
                ['Retry interval', `${config.data?.calling_policy.retry_interval_minutes} minutes`],
                ['Calling window', `${config.data?.calling_policy.window_start_hour}:00–${config.data?.calling_policy.window_end_hour}:00 ${config.data?.calling_policy.timezone}`],
              ]} />
              <p className="mt-4 text-xs text-slate-500">
                {telephony
                  ? <>Webhook URL for ElevenLabs post-call webhooks: <code>{window.location.origin.replace(':5173', ':8000')}/api/v1/screening/webhooks/elevenlabs/</code> (must be publicly reachable, e.g. via a tunnel).</>
                  : <>Set <code>SCREENING_VOICE_MODE=telephony</code> and the Twilio settings in <code>backend/.env</code> to enable real phone calls. Nothing here is required for browser voice screening.</>}
              </p>
            </Card>
          </>
        )}
        {isAdmin && config.data?.agent_system_prompt && (
          <Card title={`ElevenLabs agent configuration — ${telephony ? 'phone' : 'browser'} script (copy into the agent)`}>
            <p className="mb-2 text-sm text-slate-600">Dynamic variables sent with every session: {config.data.dynamic_variables.map((v) => <code key={v} className="mr-1 rounded bg-slate-100 px-1">{`{{${v}}}`}</code>)}</p>
            <h4 className="mt-3 text-xs font-semibold text-slate-500 uppercase">First message</h4>
            <pre className="mt-1 rounded bg-slate-50 p-3 text-xs whitespace-pre-wrap">{config.data.agent_first_message}</pre>
            <h4 className="mt-3 text-xs font-semibold text-slate-500 uppercase">System prompt</h4>
            <pre className="mt-1 rounded bg-slate-50 p-3 text-xs whitespace-pre-wrap">{config.data.agent_system_prompt}</pre>
          </Card>
        )}
        {isAdmin && (
          <Card title="Azure OpenAI (GPT-5 mini)">
            {llm.isLoading ? <Loading /> : llm.data ? (
              <KeyValue items={[['Configured', yes(llm.data.configured)], ['Deployment', String(llm.data.deployment ?? '—')], ['API', String(llm.data.api_style)]]} />
            ) : <ErrorAlert error={llm.error} />}
          </Card>
        )}
      </div>
    </>
  )
}
