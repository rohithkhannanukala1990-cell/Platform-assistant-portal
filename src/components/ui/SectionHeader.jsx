export default function SectionHeader({ title, icon: Icon, iconColor = 'text-accent', hint, actions }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2 min-w-0">
        {Icon && <Icon className={`w-4 h-4 shrink-0 ${iconColor}`} />}
        <h2 className="text-sm font-bold text-white truncate">{title}</h2>
        {hint && <span className="text-[10px] text-slate-500 truncate hidden sm:inline">— {hint}</span>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  )
}
