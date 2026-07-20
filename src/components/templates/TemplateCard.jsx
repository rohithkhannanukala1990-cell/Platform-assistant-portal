import {
  Zap,
  Eye,
  Star,
  Edit2,
  Copy,
} from 'lucide-react'
import { PermissionGate } from '../PermissionGate'

function envBadgeClass(env) {
  const e = (env || '').toLowerCase()
  if (e === 'production' || e === 'dr') return 'bg-rose-500/15 text-rose-200 border-rose-500/30'
  if (e === 'staging') return 'bg-amber-500/15 text-amber-200 border-amber-500/30'
  return 'bg-slate-500/15 text-slate-200 border-slate-500/30'
}

function toolCountForCard(t) {
  return t.tool_count ?? (Array.isArray(t.tools_preview) ? t.tools_preview.length : 0)
}

/**
 * Single template tile in the gallery grid.
 * onSelect → Apply; onPreview → Preview. Optional admin callbacks preserve existing actions.
 */
export default function TemplateCard({
  template: t,
  onSelect,
  onPreview,
  onEdit,
  onDuplicate,
  isAdmin = false,
}) {
  const previews = t.tools_preview || []
  const tc = toolCountForCard(t)
  const more = tc > 5 ? tc - 5 : 0

  return (
    <div
      className="group relative rounded-xl border border-border bg-card/40 overflow-hidden hover:border-slate-500/80 transition-colors flex flex-col min-h-[180px]"
      style={{ borderLeftWidth: 4, borderLeftColor: t.color || '#6366f1' }}
    >
      <div className="p-4 flex flex-col flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-3xl shrink-0" aria-hidden>
              {t.icon || '📋'}
            </span>
            <h3 className="font-bold text-white truncate">{t.name}</h3>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            {t.is_published ? (
              <span className="text-[10px] font-semibold text-emerald-400 whitespace-nowrap">🟢 Live</span>
            ) : (
              <span className="text-[10px] font-semibold text-slate-500 whitespace-nowrap">⚪ Draft</span>
            )}
            {(t.use_count || 0) > 5 ? (
              <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400/30" aria-label="Popular" />
            ) : null}
          </div>
        </div>
        <p className="text-sm text-slate-400 mt-2 line-clamp-2 flex-1">{t.description || '—'}</p>
        <div className="flex flex-wrap items-center gap-1.5 mt-3 min-h-[28px]">
          {previews.slice(0, 5).map((p) => (
            <span key={p.tool_id} className="text-lg" title={p.name}>
              {p.icon || '🔧'}
            </span>
          ))}
          {more > 0 ? (
            <span className="text-xs text-slate-500 font-medium">+{more} more</span>
          ) : null}
          {previews.length === 0 && tc === 0 ? (
            <span className="text-xs text-slate-600">No tools</span>
          ) : null}
        </div>
        <div className="flex items-center justify-between mt-3 text-xs text-slate-500 gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 capitalize">{t.category}</span>
            <span
              className={`px-2 py-0.5 rounded-md border text-[10px] font-semibold uppercase ${envBadgeClass(t.environment)}`}
            >
              {t.environment}
            </span>
          </div>
          <span>{t.use_count ?? 0} uses</span>
        </div>
        <div className="flex flex-wrap gap-1 mt-2">
          {(t.tags || []).slice(0, 3).map((tag) => (
            <span key={tag} className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-400">
              {tag}
            </span>
          ))}
        </div>
      </div>
      <div className="absolute inset-x-0 bottom-0 p-2 bg-slate-950/95 border-t border-border opacity-0 group-hover:opacity-100 transition-opacity flex flex-wrap gap-1 justify-end">
        <button
          type="button"
          className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-emerald-600/90 text-white text-xs font-semibold"
          onClick={() => onSelect?.(t)}
        >
          <Zap className="w-3.5 h-3.5" />
          Apply
        </button>
        <button
          type="button"
          className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-slate-700 text-xs text-white"
          onClick={() => onPreview?.(t)}
        >
          <Eye className="w-3.5 h-3.5" />
          Preview
        </button>
        {isAdmin ? (
          <>
            <PermissionGate resource="templates" action="update">
              <button
                type="button"
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-slate-700 text-xs text-white"
                onClick={() => onEdit?.(t)}
              >
                <Edit2 className="w-3.5 h-3.5" />
                Edit
              </button>
            </PermissionGate>
            <PermissionGate resource="templates" action="create">
              <button
                type="button"
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-slate-700 text-xs text-white"
                onClick={() => onDuplicate?.(t)}
              >
                <Copy className="w-3.5 h-3.5" />
                Copy
              </button>
            </PermissionGate>
          </>
        ) : null}
      </div>
    </div>
  )
}
