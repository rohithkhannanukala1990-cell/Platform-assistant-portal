const TONES = {
  neutral: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
  accent: 'bg-accent/15 text-accent border-accent/30',
  success: 'bg-success/15 text-emerald-300 border-success/30',
  warning: 'bg-warning/15 text-amber-300 border-warning/30',
  danger: 'bg-danger/15 text-red-300 border-danger/30',
}

export default function Badge({ tone = 'neutral', icon: Icon, className = '', children }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-semibold ${TONES[tone] ?? TONES.neutral} ${className}`}
    >
      {Icon && <Icon className="w-3 h-3 shrink-0" />}
      {children}
    </span>
  )
}
