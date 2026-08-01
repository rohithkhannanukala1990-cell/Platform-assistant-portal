/** Shared grounding badge for agent runs (exported for vitest). */
export function GroundingBadge({ grounding }) {
  const g = (grounding || 'none').toLowerCase()
  const styles = {
    live: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    partial: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    demo: 'bg-violet-500/15 text-violet-400 border-violet-500/30',
    none: 'bg-neutral-700/40 text-neutral-400 border-neutral-600',
  }
  return (
    <span
      data-testid="grounding-badge"
      data-grounding={g}
      className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold border ${styles[g] || styles.none}`}
    >
      grounding: {g}
    </span>
  )
}

export function AgentApproveRejectButtons({ busy, onApprove, onReject }) {
  return (
    <div className="flex gap-2 pt-1" data-testid="hitl-actions">
      <button
        type="button"
        data-testid="approve-btn"
        disabled={!!busy}
        onClick={onApprove}
        className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-emerald-600/20 border border-emerald-500/40 text-emerald-300 text-xs font-bold hover:bg-emerald-600/30 disabled:opacity-40 disabled:pointer-events-none"
      >
        Approve
      </button>
      <button
        type="button"
        data-testid="reject-btn"
        disabled={!!busy}
        onClick={onReject}
        className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-bold hover:bg-red-500/20 disabled:opacity-40 disabled:pointer-events-none"
      >
        Reject
      </button>
    </div>
  )
}
