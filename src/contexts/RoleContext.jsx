import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { useAuth } from './AuthContext'

export const ROLES = {
  Admin:             { id: 'Admin',             label: 'Admin',               emoji: '🛡️',  portal: '/ops',       color: 'text-purple-400', bg: 'bg-purple-500/15 border-purple-500/30' },
  Developer:         { id: 'Developer',         label: 'Developer',           emoji: '💻',  portal: '/developer', color: 'text-blue-400',   bg: 'bg-blue-500/15 border-blue-500/30' },
  DataEngineer:      { id: 'DataEngineer',      label: 'Data Engineer',       emoji: '📊',  portal: '/data',      color: 'text-cyan-400',   bg: 'bg-cyan-500/15 border-cyan-500/30' },
  NetworkEngineer:   { id: 'NetworkEngineer',   label: 'Network Engineer',    emoji: '🌐',  portal: '/ops',       color: 'text-amber-400',  bg: 'bg-amber-500/15 border-amber-500/30' },
  DatabaseDeveloper: { id: 'DatabaseDeveloper', label: 'Database Developer',  emoji: '🗄️',  portal: '/database',  color: 'text-rose-400',   bg: 'bg-rose-500/15 border-rose-500/30' },
}

const RoleContext = createContext(null)

export function RoleProvider({ children }) {
  const { role: jwtRole, user, isAuthenticated } = useAuth()
  const isDev = import.meta.env.DEV

  const [activeRole, setActiveRole] = useState(() => {
    try {
      return localStorage.getItem('aiops_active_role') || null
    } catch {
      return null
    }
  })

  // When auth role changes (login/logout), reset the active persona.
  useEffect(() => {
    setActiveRole(null)
    try {
      localStorage.removeItem('aiops_active_role')
    } catch {
      // ignore storage failures
    }
  }, [jwtRole, isAuthenticated])

  const role = useMemo(() => {
    const baseRole = jwtRole ?? (isDev ? 'Admin' : null)
    if (!baseRole) return null

    // Only Admin can switch personas.
    if (baseRole !== 'Admin') return baseRole

    return ROLES[activeRole]?.id ? activeRole : baseRole
  }, [jwtRole, isDev, activeRole])

  const roleInfo = ROLES[role] ?? ROLES['Admin']

  function setRole(nextRole) {
    const baseRole = jwtRole ?? (isDev ? 'Admin' : null)
    if (baseRole !== 'Admin') return
    if (!ROLES[nextRole]) return
    setActiveRole(nextRole)
    try {
      localStorage.setItem('aiops_active_role', nextRole)
    } catch {
      // ignore storage failures
    }
  }

  return (
    <RoleContext.Provider value={{ role, setRole, roleInfo, user, isAuthenticated }}>
      {children}
    </RoleContext.Provider>
  )
}

export function useRole() {
  const ctx = useContext(RoleContext)
  if (!ctx) throw new Error('useRole must be used inside <RoleProvider>')
  return ctx
}
