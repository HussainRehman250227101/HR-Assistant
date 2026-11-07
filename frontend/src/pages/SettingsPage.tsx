import { useAgentConfig, useLLMStatus } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Badge, Card, ErrorAlert, KeyValue, Loading, PageHeader } from '../components/ui'

const yes = (v: unknown) => <Badge value={v ? 'COMPLETED' : 'FAILED'} label={v ? 'Configured' : 'Missing'} />

export function SettingsPage() {
  const { isAdmin } = useAuth()
  const config = useAgentConfig()
  const llm = useLLMStatus(isAdmin)
  const i = config.data?.integration
  return (
    <>
      <PageHeader title="Integrations" subtitle="Server-side configuration status. Secrets are never sent to the browser — only whether each one is set." />
      <div className="space-y-6">
        <ErrorAlert error={config.error} />
        {config.isLoading ? <Loading /> : i && (
          <Card title="Voice screening — Twilio + ElevenLabs">
            <KeyValue items={[
              ['Telephony provider', String(i.telephony_provider)], ['Voice AI provider', String(i.voice_ai_provider)],
              ['ElevenLabs API key', yes(i.elevenlabs_api_key)], ['ElevenLabs agent ID', yes(i.elevenlabs_agent_id)],
              ['ElevenLabs phone-number ID (imported Twilio number)', yes(i.elevenlabs_agent_phone_number_id)],
              ['Webhook secret', yes(i.elevenlabs_webhook_secret)], ['Twilio account SID', yes(i.twilio_account_sid)],
              ['Twilio auth token', yes(i.twilio_auth_token)], ['Twilio phone number', yes(i.twilio_phone_number)],
              ['Allowed destinations', (i.allowed_dial_prefixes as string[]).join(', ')],
              ['Max attempts', String(config.data?.calling_policy.max_attempts)],
              ['Retry interval', `${config.data?.calling_policy.retry_interval_minutes} minutes`],
              ['Calling window', `${config.data?.calling_policy.window_start_hour}:00–${config.data?.calling_policy.window_end_hour}:00 ${config.data?.calling_policy.timezone}`],
              ['Approved script', config.data?.script_version],
            ]} />
            <p className="mt-4 text-xs text-slate-500">Webhook URL for ElevenLabs post-call webhooks: <code>{window.location.origin.replace(':5173', ':8000')}/api/v1/screening/webhooks/elevenlabs/</code> (must be publicly reachable, e.g. via a tunnel).</p>
          </Card>
        )}
        {isAdmin && config.data?.agent_system_prompt && (
          <Card title="ElevenLabs agent configuration (copy into the agent)">
            <p className="mb-2 text-sm text-slate-600">Dynamic variables sent with every call: {config.data.dynamic_variables.map((v) => <code key={v} className="mr-1 rounded bg-slate-100 px-1">{`{{${v}}}`}</code>)}</p>
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
