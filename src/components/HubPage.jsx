import { useNavigate } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { PageHeader } from './ui'

/**
 * Generic card-grid landing page that groups related tool views
 * under a single sidebar entry.
 */
export default function HubPage({ title, subtitle, items }) {
  const navigate = useNavigate()

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      <PageHeader title={title} subtitle={subtitle} />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {items.map(({ label, description, path, icon: Icon }) => (
          <button
            key={path}
            type="button"
            onClick={() => navigate(path)}
            className="group flex items-start gap-4 p-5 rounded-2xl border border-border bg-card text-left transition-colors hover:border-accent/40 hover:bg-card/80"
          >
            <div className="flex items-center justify-center w-11 h-11 rounded-xl bg-accent/15 text-accent shrink-0">
              <Icon className="w-5 h-5" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-white flex items-center gap-1">
                {label}
                <ChevronRight className="w-3.5 h-3.5 text-slate-600 transition-transform group-hover:translate-x-0.5 group-hover:text-accent" />
              </p>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">{description}</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
