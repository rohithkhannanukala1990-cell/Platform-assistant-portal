export default function Card({ title, icon: Icon, iconColor = 'text-accent', actions, padding = 'p-5', className = '', children }) {
  return (
    <div className={`flex flex-col rounded-2xl border border-border bg-card ${padding} ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-2 mb-4">
          <div className="flex items-center gap-2 min-w-0">
            {Icon && <Icon className={`w-4 h-4 shrink-0 ${iconColor}`} />}
            {title && <h3 className="text-sm font-bold text-white truncate">{title}</h3>}
          </div>
          {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  )
}
