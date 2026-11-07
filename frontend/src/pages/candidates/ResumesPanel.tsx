import { useState } from 'react'
import { useResumeAction, useUploadResume } from '../../api/hooks'
import { Alert, Badge, Button, Card, Empty, ErrorAlert, Table, Td } from '../../components/ui'
import { downloadFile } from '../../lib/api'
import { formatBytes, formatDate } from '../../lib/format'
import type { Candidate } from '../../lib/types'

export function ResumesPanel({ candidate, canEdit }: { candidate: Candidate; canEdit: boolean }) {
  const upload = useUploadResume(candidate.public_id)
  const action = useResumeAction()
  const [file, setFile] = useState<File | null>(null)
  const [downloadError, setDownloadError] = useState<unknown>(null)

  return (
    <Card title="Resumes" actions={canEdit && candidate.current_status !== 'CLOSED' && (
      <div className="flex items-center gap-2">
        <input type="file" accept=".pdf,.docx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-xs" />
        <Button size="sm" disabled={!file} loading={upload.isPending} onClick={async () => { await upload.mutateAsync(file!); setFile(null) }}>Upload</Button>
      </div>
    )}>
      <div className="space-y-3">
        <ErrorAlert error={upload.error ?? action.error ?? downloadError} />
        {!candidate.resume_documents.length ? <Empty>No resume uploaded.</Empty> : (
          <Table head={['File', 'Status', 'Uploaded', 'Notes', '']}>
            {candidate.resume_documents.map((d) => (
              <tr key={d.public_id}>
                <Td><div className="font-medium">{d.original_filename}</div><div className="text-xs text-slate-500">{formatBytes(d.file_size)}</div></Td>
                <Td><Badge value={d.processing_status} /></Td>
                <Td>{formatDate(d.created_at)}</Td>
                <Td className="max-w-xs text-xs">
                  {d.error_message && <div className="text-rose-700">{d.error_message}</div>}
                  {d.warning_messages.map((w) => <div key={w} className="text-amber-700">{w}</div>)}
                </Td>
                <Td className="space-x-1 whitespace-nowrap">
                  {canEdit && d.processing_status === 'PENDING' && (
                    <Button size="sm" loading={action.isPending && action.variables?.id === d.public_id} onClick={() => action.mutate({ id: d.public_id, action: 'process' })}>Extract text</Button>
                  )}
                  {canEdit && d.processing_status === 'FAILED' && (
                    <Button size="sm" variant="secondary" onClick={() => action.mutate({ id: d.public_id, action: 'retry' })}>Retry</Button>
                  )}
                  {canEdit && (
                    <Button size="sm" variant="ghost" onClick={() => downloadFile(`/candidates/resume-documents/${d.public_id}/download/`, d.original_filename).catch(setDownloadError)}>Download</Button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
        {candidate.resume_documents.some((d) => d.processing_status === 'NEEDS_MANUAL_REVIEW') && (
          <Alert tone="warning">A resume could not be read automatically (scanned, protected or corrupt). Upload a text-based PDF/DOCX; content is never guessed.</Alert>
        )}
      </div>
    </Card>
  )
}
