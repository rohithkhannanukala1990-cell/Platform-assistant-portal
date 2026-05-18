import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, LogOut } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import AdminOverview from './AdminOverview'
import UserManagement from './UserManagement'
import AgentPermissions from './AgentPermissions'
import AuditLogView from './AuditLogView'
import SettingsModal from '../SettingsModal'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'users', label: 'Users' },
  { id: 'agents', label: 'Agents' },
  { id: 'audit', label: 'Audit' },
  { id: 'settings', label: 'Settings' },
]

export default function AdminDashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [tab, setTab] = useState('overview')

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 flex flex-col">
      <header className="border-b border-neutral-800 px-6 py-4 flex items-center justify-between bg-neutral-900/80">
        <div className="flex items-center gap-3">
          <ShieldCheck className="w-6 h-6 text-violet-400" />
          <div>
            <h1 className="text-lg font-semibold text-white">Admin Console</h1>
            <p className="text-xs text-neutral-500">
              Signed in as <span className="text-neutral-300">{user?.username}</span>
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/dashboard')}
            className="text-sm text-neutral-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-neutral-800"
          >
            Back to Portal
          </button>
          <button
            type="button"
            onClick={handleLogout}
            className="flex items-center gap-2 text-sm text-neutral-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-neutral-800"
          >
            <LogOut className="w-4 h-4" />
            Logout
          </button>
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        <aside className="w-52 border-r border-neutral-800 bg-neutral-900/50 py-4 shrink-0">
          <nav className="flex flex-col gap-1 px-2">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                  tab === t.id
                    ? 'bg-violet-600 text-white font-medium'
                    : 'text-neutral-400 hover:bg-neutral-800 hover:text-white'
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </aside>

        <main className="flex-1 overflow-auto p-6">
          {tab === 'overview' && <AdminOverview />}
          {tab === 'users' && <UserManagement />}
          {tab === 'agents' && <AgentPermissions />}
          {tab === 'audit' && <AuditLogView />}
          {tab === 'settings' && (
            <div className="max-w-2xl">
              <SettingsModal embedded onClose={() => {}} />
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
