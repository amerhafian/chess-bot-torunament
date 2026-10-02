import { Link, NavLink } from 'react-router-dom'
import type { ReactNode } from 'react'

export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-[rgba(92,58,26,0.15)] bg-[rgba(247,239,228,0.85)] backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link to="/" className="group flex items-baseline gap-2">
            <span className="font-display text-2xl font-bold text-[var(--color-felt-deep)] transition-colors group-hover:text-[var(--color-felt)]">
              Chess Bot Tournament
            </span>
          </Link>
          <nav className="flex items-center gap-1 text-sm font-medium sm:gap-2">
            <NavItem to="/tournament">Tournament</NavItem>
            <NavItem to="/play">Play</NavItem>
            <NavItem to="/weights">Weights</NavItem>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">{children}</main>
    </div>
  )
}

function NavItem({ to, children }: { to: string; children: ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `rounded-md px-3 py-1.5 transition-colors ${
          isActive
            ? 'bg-[var(--color-felt)] text-[#f5f0e6]'
            : 'text-[var(--color-ink-soft)] hover:bg-[rgba(139,90,43,0.1)]'
        }`
      }
    >
      {children}
    </NavLink>
  )
}

export function StatusPill({ status }: { status: string }) {
  const colors: Record<string, string> = {
    running: 'bg-emerald-100 text-emerald-900',
    pending: 'bg-amber-100 text-amber-900',
    finished: 'bg-stone-200 text-stone-800',
    cancelled: 'bg-rose-100 text-rose-900',
    active: 'bg-emerald-100 text-emerald-900',
  }
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${colors[status] || 'bg-stone-100 text-stone-700'}`}>
      {status}
    </span>
  )
}
