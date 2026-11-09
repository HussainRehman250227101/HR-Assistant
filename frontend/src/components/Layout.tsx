import type { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { humanize } from '../lib/format'

/** 20px stroke icons (Lucide-style paths), inherits currentColor. */
function Icon({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden className="shrink-0">
      {children}
    </svg>
  )
}

const ICONS = {
  dashboard: <Icon><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></Icon>,
  requisitions: <Icon><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></Icon>,
  candidates: <Icon><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.6-3.4 3.2-5.5 6.5-5.5s5.9 2.1 6.5 5.5" /><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.8c1.9.8 3.1 2.6 3.5 5.2" /></Icon>,
  shortlist: <Icon><path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z" /></Icon>,
  screening: <Icon><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></Icon>,
  interviews: <Icon><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></Icon>,
  schedule: <Icon><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Icon>,
  audit: <Icon><path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z" /><path d="M9 12l2 2 4-4" /></Icon>,
  integrations: <Icon><path d="M9 3v5M15 3v5M7 8h10v4a5 5 0 0 1-10 0zM12 17v4" /></Icon>,
}

type NavItem = { to: string; label: string; icon: keyof typeof ICONS; end?: boolean; staff?: boolean }
const SECTIONS: { title: string; items: NavItem[] }[] = [
  { title: 'Overview', items: [{ to: '/', label: 'Dashboard', icon: 'dashboard', end: true, staff: true }] },
  {
    title: 'Hiring pipeline',
    items: [
      { to: '/requisitions', label: 'Requisitions', icon: 'requisitions', staff: true },
      { to: '/candidates', label: 'Candidates', icon: 'candidates' },
      { to: '/shortlist', label: 'Shortlist Review', icon: 'shortlist', staff: true },
      { to: '/screening', label: 'Screening', icon: 'screening', staff: true },
      { to: '/interviews', label: 'Interviews & Availability', icon: 'interviews', staff: true },
      { to: '/my-schedule', label: 'My Schedule', icon: 'schedule' },
    ],
  },
  {
    title: 'Administration',
    items: [
      { to: '/activity', label: 'Audit Log', icon: 'audit', staff: true },
      { to: '/settings', label: 'Integrations', icon: 'integrations', staff: true },
    ],
  },
]

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '?') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}

export function Layout() {
  const { user, logout, hasFullAccess } = useAuth()
  const displayName = user ? user.full_name || user.username : ''
  return (
    <div className="min-h-screen bg-slate-50 md:flex">
      <aside className="flex flex-col bg-gradient-to-b from-slate-900 to-slate-950 text-slate-100 md:sticky md:top-0 md:h-screen md:w-64 md:shrink-0">
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-400 to-indigo-600 text-sm font-bold text-white shadow-lg shadow-indigo-900/40">HR</div>
          <div className="leading-tight">
            <div className="text-[15px] font-semibold tracking-tight text-white">HR Assistant</div>
            <div className="text-[11px] text-slate-400">Human-supervised hiring</div>
          </div>
        </div>

        <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4" aria-label="Main">
          {SECTIONS.map((section) => {
            const items = section.items.filter((item) => !item.staff || hasFullAccess)
            if (!items.length) return null
            return (
              <div key={section.title}>
                <div className="px-3 pb-1.5 text-[10.5px] font-semibold tracking-widest text-slate-500 uppercase">{section.title}</div>
                <div className="space-y-0.5">
                  {items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.end}
                      className={({ isActive }) =>
                        `group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                          isActive ? 'bg-indigo-500/15 text-white' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'
                        }`
                      }
                    >
                      {({ isActive }) => (
                        <>
                          {isActive && <span className="absolute top-1.5 bottom-1.5 left-0 w-1 rounded-r bg-indigo-400" />}
                          <span className={isActive ? 'text-indigo-300' : 'text-slate-500 group-hover:text-slate-300'}>{ICONS[item.icon]}</span>
                          {item.label}
                        </>
                      )}
                    </NavLink>
                  ))}
                </div>
              </div>
            )
          })}
        </nav>

        {user && (
          <div className="m-3 flex items-center gap-3 rounded-xl bg-white/5 p-3 ring-1 ring-white/5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-indigo-500/30 text-xs font-semibold text-indigo-100">{initials(displayName)}</div>
            <div className="min-w-0 flex-1 leading-tight">
              <div className="truncate text-sm font-medium text-white">{displayName}</div>
              <div className="truncate text-[11px] text-slate-400">{user.is_superuser ? 'Superuser' : humanize(user.role)}</div>
            </div>
            <button onClick={logout} title="Sign out" aria-label="Sign out" className="rounded-md p-1.5 text-slate-400 hover:bg-white/10 hover:text-white">
              <Icon><path d="M9 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M16 8l4 4-4 4M20 12H9" /></Icon>
            </button>
          </div>
        )}
      </aside>
      <main className="min-w-0 flex-1 overflow-x-hidden p-4 md:p-8">
        <div className="mx-auto max-w-7xl">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
