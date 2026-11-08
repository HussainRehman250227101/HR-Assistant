import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { Layout } from './components/Layout'
import { Loading } from './components/ui'
import { CandidateDetailPage } from './pages/candidates/CandidateDetailPage'
import { CandidatesPage } from './pages/candidates/CandidatesPage'
import { ActivityLogPage } from './pages/ActivityLogPage'
import { DashboardPage } from './pages/DashboardPage'
import { InterviewsPage } from './pages/interviews/InterviewsPage'
import { MySchedulePage } from './pages/interviews/MySchedulePage'
import { LoginPage } from './pages/LoginPage'
import { RequisitionDetailPage } from './pages/requisitions/RequisitionDetailPage'
import { RequisitionFormPage } from './pages/requisitions/RequisitionFormPage'
import { RequisitionsPage } from './pages/requisitions/RequisitionsPage'
import { ScreeningQueuePage } from './pages/screening/ScreeningQueuePage'
import { SettingsPage } from './pages/SettingsPage'
import { ShortlistQueuePage } from './pages/ShortlistQueuePage'

// Loaded on demand so the ElevenLabs/WebRTC SDK is only downloaded when a browser voice session is opened.
const BrowserScreeningPage = lazy(() => import('./pages/screening/BrowserScreeningPage').then((m) => ({ default: m.BrowserScreeningPage })))

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <Loading label="Signing in…" />
  if (!user) return <Navigate to="/login" replace />
  return children
}

/** Pages for HR Administrators and Hiring Managers. The interviewer-only HR Recruiter goes to their schedule. */
function StaffOnly({ children }: { children: React.ReactNode }) {
  const { hasFullAccess } = useAuth()
  return hasFullAccess ? children : <Navigate to="/my-schedule" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route index element={<StaffOnly><DashboardPage /></StaffOnly>} />
        <Route path="activity" element={<StaffOnly><ActivityLogPage /></StaffOnly>} />
        <Route path="requisitions" element={<StaffOnly><RequisitionsPage /></StaffOnly>} />
        <Route path="requisitions/new" element={<StaffOnly><RequisitionFormPage /></StaffOnly>} />
        <Route path="requisitions/:ref" element={<StaffOnly><RequisitionDetailPage /></StaffOnly>} />
        <Route path="requisitions/:ref/edit" element={<StaffOnly><RequisitionFormPage /></StaffOnly>} />
        <Route path="candidates" element={<CandidatesPage />} />
        <Route path="candidates/:id" element={<CandidateDetailPage />} />
        <Route path="shortlist" element={<StaffOnly><ShortlistQueuePage /></StaffOnly>} />
        <Route path="screening" element={<StaffOnly><ScreeningQueuePage /></StaffOnly>} />
        <Route path="screening/:id/browser" element={<StaffOnly><Suspense fallback={<Loading />}><BrowserScreeningPage /></Suspense></StaffOnly>} />
        <Route path="interviews" element={<StaffOnly><InterviewsPage /></StaffOnly>} />
        <Route path="my-schedule" element={<MySchedulePage />} />
        <Route path="settings" element={<StaffOnly><SettingsPage /></StaffOnly>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
