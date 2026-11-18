import { useParams } from 'react-router-dom'
import { useScreeningInvite } from '../../api/hooks'
import { Alert, Card, Loading } from '../../components/ui'
import { BrowserVoiceSession } from './BrowserVoiceSession'

/** Public page opened from the emailed link (no login). The candidate talks to the AI screening agent in the browser. */
export function ScreeningInvitePage() {
  const { token } = useParams()
  const invite = useScreeningInvite(token)
  const info = invite.data

  return (
    <div className="mx-auto max-w-2xl space-y-4 p-6">
      {invite.isLoading ? <Loading /> : !info ? (
        <Alert>This screening link is invalid or has expired. Please contact the HR team that sent it.</Alert>
      ) : (
        <>
          <h1 className="text-xl font-semibold text-slate-900">Screening interview: {info.role_title}</h1>
          <p className="text-sm text-slate-600">
            Hello{info.candidate_first_name ? ` ${info.candidate_first_name}` : ''}, this is a short AI-led screening interview for {info.organization}.
          </p>
          {['PENDING_CALL', 'CALL_IN_PROGRESS'].includes(info.status) ? (
            <Card title="Your interview">
              <BrowserVoiceSession screening={{ public_id: info.public_id, status: info.status as never }} inviteToken={token} />
            </Card>
          ) : (
            <Alert tone="info">This interview has already been completed or is no longer available. Thank you!</Alert>
          )}
        </>
      )}
    </div>
  )
}
