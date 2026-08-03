import { Inbox } from 'lucide-react'

export default function EmptyState({ icon: Icon = Inbox, title = 'Nothing here yet', hint, action, className = '' }) {
  return (
    <div className={`flex flex-col items-center justify-center gap-2 py-10 text-center ${className}`}>
      <Icon className="w-8 h-8 text-slate-600" />
      <p className="text-sm text-slate-400">{title}</p>
      {hint && <p className="text-xs text-slate-600 max-w-xs">{hint}</p>}
      {action}
    </div>
  )
}
