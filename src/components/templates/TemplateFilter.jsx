import { Filter } from 'lucide-react'

/**
 * Category filter pills for the template gallery.
 */
export default function TemplateFilter({ activeFilter, onChange, categories = [] }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs text-slate-500 uppercase tracking-wider">
        <Filter className="w-4 h-4" aria-hidden />
        Category
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-thin">
        {categories.map((cat) => {
          const label = cat === 'all' ? 'All' : cat
          const active = activeFilter === cat
          return (
            <button
              key={cat}
              type="button"
              onClick={() => onChange?.(cat)}
              className={`shrink-0 px-4 py-2 rounded-full text-sm font-medium border transition-colors capitalize ${
                active
                  ? 'bg-blue-600 border-blue-500 text-white'
                  : 'bg-slate-900/80 border-border text-slate-300 hover:border-slate-500'
              }`}
            >
              {label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
