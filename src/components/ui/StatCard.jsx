import { useNavigate } from 'react-router-dom'

/**
 * Compact KPI card. Pass `to` to make it a navigation button,
 * omit it for a static stat.
 */
export default function StatCard({ to, icon: Icon, iconClass = 'bg-accent/15 text-accent', label, value, sub }) {
  const navigate = useNavigate()

  const inner = (
    <>
      {Icon && (
        <div className={`flex items-center justify-center w-10 h-10 rounded-xl shrink-0 ${iconClass}`}>
          <Icon className="w-5 h-5" />
        </div>
      )}
      <div className="min-w-0">
        <p className="text-2xl font-bold text-white leading-none">{value ?? '—'}</p>
        <p className="text-xs text-slate-400 mt-1 truncate">{label}</p>
        {sub && <p className="text-[10px] text-slate-600 mt-0.5 truncate">{sub}</p>}
      </div>
    </>
  )

  const base = 'flex items-center gap-4 px-5 py-4 rounded-2xl border border-border bg-card'

  if (to) {
    return (
      <button
        type="button"
        onClick={() => navigate(to)}
        className={`${base} text-left w-full transition-colors hover:border-accent/40 hover:bg-card/80`}
      >
        {inner}
      </button>
    )
  }

  return <div className={base}>{inner}</div>
}
