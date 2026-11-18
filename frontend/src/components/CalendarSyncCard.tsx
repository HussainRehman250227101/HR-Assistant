import { useState } from 'react'
import { useCalendarSubscription, useRegenerateCalendarUrl } from '../api/hooks'
import { Alert, Button, Card, ErrorAlert, Input, Loading } from './ui'

/** Private calendar-feed URL that works with Google Calendar, Outlook and Apple Calendar (one-way: HR app -> calendar). */
export function CalendarSyncCard() {
  const sub = useCalendarSubscription()
  const regenerate = useRegenerateCalendarUrl()
  const [copied, setCopied] = useState(false)
  const url = sub.data?.url ?? ''

  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <Card title="Sync my interviews with Google or Outlook Calendar">
      <div className="space-y-4">
        <p className="text-sm text-slate-600">
          Subscribe to this private link and your assigned interviews appear in your own calendar and move or disappear when they change here
          (calendars refresh every few hours).
        </p>
        <ErrorAlert error={sub.error ?? regenerate.error} />
        {sub.isLoading ? <Loading /> : (
          <div className="flex flex-wrap items-center gap-2">
            <Input readOnly value={url} onFocus={(e) => e.target.select()} className="min-w-0 flex-1" aria-label="Calendar subscription link" />
            <Button variant="secondary" onClick={copy}>{copied ? 'Copied' : 'Copy link'}</Button>
          </div>
        )}
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
          <li><strong>Google Calendar:</strong> Other calendars (+) → From URL → paste the link.</li>
          <li><strong>Outlook:</strong> Add calendar → Subscribe from web → paste the link.</li>
          <li><strong>Apple Calendar:</strong> File → New Calendar Subscription → paste the link.</li>
        </ul>
        <Alert tone="info">
          Keep the link private: anyone who has it can see your interview times and candidate names. If it leaks, generate a new one (the old link stops working).
          The link only works if this application is reachable from the internet.
        </Alert>
        <Button variant="secondary" size="sm" loading={regenerate.isPending}
          onClick={() => { if (confirm('Generate a new link? The current link will stop working and you must subscribe again.')) regenerate.mutate() }}>
          Generate a new link
        </Button>
      </div>
    </Card>
  )
}
