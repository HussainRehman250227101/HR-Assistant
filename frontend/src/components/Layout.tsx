import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { humanize } from '../lib/format'

const NAV = [
  { to: '/', label: 'Dashboard', end: true, staff: true },
  { to: '/requisitions', label: 'Requisitions', staff: true },
  { to: '/candidates', label: 'Candidates' },
  { to: '/shortlist', label: 'Shortlist Review', staff: true },
  { to: '/screening', label: 'Screening', staff: true },
  { to: '/interviews', label: 'Interviews & Availability', staff: true },
  { to: '/my-schedule', label: 'My Schedule' },
  { to: '/activity', label: 'Audit Log', staff: true },
  { to: '/settings', label: 'Integrations', staff: true },
] as { to: string; label: string; end?: boolean; staff?: boolean }[]

export function Layout() {
  const { user, logout, hasFullAccess } = useAuth()
  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-slate-200 bg-slate-900 text-slate-100 md:min-h-screen md:w-60 md:border-r md:border-b-0">
        <div className="px-5 py-4">
          <div className="text-base font-semibold">HR Assistant</div>
          <div className="text-xs text-slate-400">Human-supervised hiring workflow</div>
        </div>
        <nav className="flex flex-wrap gap-1 px-3 pb-3 md:flex-col">
          {NAV.filter((item) => !item.staff || hasFullAccess).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm ${isActive ? 'bg-slate-700 text-white' : 'text-slate-300 hover:bg-slate-800'}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        {user && (
          <div className="border-t border-slate-800 px-5 py-4 text-xs text-slate-400">
            <div className="text-sm text-slate-100">{user.full_name || user.username}</div>
            <div>{user.is_superuser ? 'Superuser' : humanize(user.role)}</div>
            <button onClick={logout} className="mt-2 text-indigo-300 hover:text-indigo-200">
              Sign out
            </button>
          </div>
        )}
      </aside>
      <main className="flex-1 overflow-x-hidden p-4 md:p-8">
        <Outlet />
      </main>
    </div>
  )
}
