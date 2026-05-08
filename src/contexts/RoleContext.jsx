import { createContext, useContext } from 'react'
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
  const role = jwtRole ?? (isDev ? 'Admin' : null)
  const roleInfo = ROLES[role] ?? ROLES['Admin']

  return (
    <RoleContext.Provider value={{ role, roleInfo, user, isAuthenticated }}>
      {children}
    </RoleContext.Provider>
  )
}

export function useRole() {
  const ctx = useContext(RoleContext)
  if (!ctx) throw new Error('useRole must be used inside <RoleProvider>')
  return ctx
}
