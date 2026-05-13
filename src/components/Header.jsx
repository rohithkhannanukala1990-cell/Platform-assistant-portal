import { Settings } from 'lucide-react'
import PersonaSwitcher from './PersonaSwitcher'
import NotificationDropdown from './NotificationDropdown'
import UserMenu from './UserMenu'
import WorkspaceSwitcher from './WorkspaceSwitcher'
import AccountSwitcher from './AccountSwitcher'
import EnvironmentSwitcher from './EnvironmentSwitcher'

export default function Header({
  breadcrumbLeft,
  showOpsChrome,
  opsToolId,
  showHealthButton,
  healthStatus,
  onOpenHealthDashboard,
  onOpenSettings,
  onLogout,
  onSelectIncident,
}) {
  return (
    <header className="flex items-center gap-4 px-6 py-3.5 border-b border-border bg-sidebar shrink-0">
      <div className="flex items-center gap-2 min-w-0 flex-1 justify-start">
        <span className="text-xs font-medium text-slate-500">Platform Engineering</span>
        <span className="text-slate-700">/</span>
        {breadcrumbLeft}
      </div>

      <div className="flex-1 min-w-[8px]" aria-hidden />

      {showOpsChrome && (
        <div className="flex items-center gap-2 shrink-0">
          <WorkspaceSwitcher />
          {opsToolId ? (
            <AccountSwitcher toolId={opsToolId} onAccountChanged={() => {}} />
          ) : null}
          <EnvironmentSwitcher />
        </div>
      )}

      <div className="flex items-center gap-3 shrink-0 justify-end">
        <PersonaSwitcher />

        <NotificationDropdown
          onSelectIncident={onSelectIncident}
          onOpenHealthDashboard={onOpenHealthDashboard}
        />

        {showHealthButton && (
          <button
            type="button"
            title={
              healthStatus === 'critical'
                ? 'System issues detected — click to view'
                : 'System health'
            }
            onClick={onOpenHealthDashboard}
            className="relative flex items-center justify-center w-8 h-8 rounded-full border border-border hover:bg-card transition-colors"
            aria-label="Open system health"
          >
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                healthStatus === 'critical'
                  ? 'bg-red-500 animate-pulse'
                  : healthStatus === 'warning'
                    ? 'bg-yellow-400 animate-pulse'
                    : 'bg-green-500'
              }`}
            />
          </button>
        )}

        <button
          type="button"
          onClick={onOpenSettings}
          className="p-2 rounded-lg hover:bg-card transition-colors group"
          title="Settings"
        >
          <Settings className="w-4 h-4 text-slate-400 group-hover:text-white transition-colors" />
        </button>

        <UserMenu onLogout={onLogout} onOpenSettings={onOpenSettings} />
      </div>
    </header>
  )
}
