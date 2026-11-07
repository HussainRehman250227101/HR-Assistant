import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { Layout } from './components/Layout'
import { Loading } from './components/ui'
import { CandidateDetailPage } from './pages/candidates/CandidateDetailPage'
import { CandidatesPage } from './pages/candidates/CandidatesPage'
import { ActivityLogPage } from './pages/ActivityLogPage'
import { DashboardPage } from './pages/DashboardPage'
import { InterviewsPage } from './pages/interviews/InterviewsPage'
import { LoginPage } from './pages/LoginPage'
import { RequisitionDetailPage } from './pages/requisitions/RequisitionDetailPage'
import { RequisitionFormPage } from './pages/requisitions/RequisitionFormPage'
import { RequisitionsPage } from './pages/requisitions/RequisitionsPage'
import { ScreeningQueuePage } from './pages/screening/ScreeningQueuePage'
import { SettingsPage } from './pages/SettingsPage'
import { ShortlistQueuePage } from './pages/ShortlistQueuePage'

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <Loading label="Signing in…" />
  if (!user) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route index element={<DashboardPage />} />
        <Route path="activity" element={<ActivityLogPage />} />
        <Route path="requisitions" element={<RequisitionsPage />} />
        <Route path="requisitions/new" element={<RequisitionFormPage />} />
        <Route path="requisitions/:ref" element={<RequisitionDetailPage />} />
        <Route path="requisitions/:ref/edit" element={<RequisitionFormPage />} />
        <Route path="candidates" element={<CandidatesPage />} />
        <Route path="candidates/:id" element={<CandidateDetailPage />} />
        <Route path="shortlist" element={<ShortlistQueuePage />} />
        <Route path="screening" element={<ScreeningQueuePage />} />
        <Route path="interviews" element={<InterviewsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
