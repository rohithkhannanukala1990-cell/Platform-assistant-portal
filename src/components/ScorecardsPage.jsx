import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ClipboardCheck,
  Search,
  Loader2,
  RefreshCw,
  X,
  ChevronDown,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const CATEGORIES = ['Documentation', 'Reliability', 'Security', 'Ownership']

const KIND_BADGE = {
  Service: 'bg-blue-600',
  API: 'bg-green-600',
  Library: 'bg-yellow-600',
  Website: 'bg-purple-600',
  Team: 'bg-slate-600',
}

const FILTER_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'passing', label: 'Passing (≥70)' },
  { value: 'warning', label: 'Warning (50–69)' },
  { value: 'failing', label: 'Failing (<50)' },
  { value: 'none', label: 'Not Evaluated' },
]

function hasEvaluation(scorecard) {
  return (scorecard?.checks?.length ?? 0) > 0
}

function categoryScores(scorecard) {
  const out = {}
  for (const cat of CATEGORIES) {
    const checks = (scorecard?.checks ?? []).filter((c) => c.category === cat)
    out[cat] = checks.length
      ? Math.round(checks.reduce((s, c) => s + (c.score ?? 0), 0) / checks.length)
      : 0
  }
  return out
}

function barColor(score) {
  if (score >= 80) return 'bg-emerald-500'
  if (score >= 50) return 'bg-amber-500'
  return 'bg-red-500'
}

function ScoreRing({ score, size = 72 }) {
  const radius = 28
  const circ = 2 * Math.PI * radius
  const pct = Math.min(100, Math.max(0, score)) / 100
  const color = score >= 80 ? '#22c55e' : score >= 50 ? '#f59e0b' : '#ef4444'
  return (
    <svg width={size} height={size} viewBox="0 0 72 72" className="shrink-0">
      <circle cx="36" cy="36" r={radius} fill="none" stroke="#374151" strokeWidth="6" />
      <circle
        cx="36"
        cy="36"
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth="6"
        strokeDasharray={`${pct * circ} ${circ}`}
        strokeLinecap="round"
        transform="rotate(-90 36 36)"
      />
      <text x="36" y="41" textAnchor="middle" fontSize="14" fontWeight="bold" fill={color}>
        {score}
      </text>
    </svg>
  )
}

function KindBadge({ kind }) {
  return (
    <span
      className={`text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded text-white ${
        KIND_BADGE[kind] || 'bg-slate-600'
      }`}
    >
      {kind || 'Unknown'}
    </span>
  )
}

function LifecycleBadge({ lifecycle }) {
  const cls =
    lifecycle === 'production'
      ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
      : lifecycle === 'deprecated'
        ? 'text-red-400 border-red-500/30 bg-red-500/10'
        : 'text-amber-400 border-amber-500/30 bg-amber-500/10'
  return (
    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${cls}`}>
      {lifecycle || 'unknown'}
    </span>
  )
}

function CheckStatusDot({ status }) {
  if (status === 'pass') return <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
  if (status === 'fail') return <span className="w-2 h-2 rounded-full bg-red-500 shrink-0" />
  return <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
}

function statusLabel(status) {
  if (status === 'pass') return 'PASS'
  if (status === 'fail') return 'FAIL'
  return 'WARN'
}

function KpiCard({ label, value, border }) {
  return (
    <div className={`rounded-2xl border ${border} bg-card px-5 py-4`}>
      <p className="text-2xl font-bold text-white">{value}</p>
      <p className="text-xs text-slate-400 mt-1">{label}</p>
    </div>
  )
}

function SkeletonCard() {
  return <div className="rounded-2xl border border-border bg-card p-5 h-56 animate-pulse" />
}

function CategoryBars({ scores }) {
  return (
    <div className="space-y-2 w-full">
      {CATEGORIES.map((cat) => {
        const s = scores[cat] ?? 0
        return (
          <div key={cat}>
            <div className="flex justify-between text-[10px] text-slate-500 mb-0.5">
              <span>{cat}</span>
              <span>{s}</span>
            </div>
            <div className="h-1.5 rounded-full bg-slate-800 overflow-hidden">
              <div
                className={`h-full rounded-full ${barColor(s)}`}
                style={{ width: `${s}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function ScorecardsPage() {
  const { authFetch } = useAuth()
  const [entities, setEntities] = useState([])
  const [cards, setCards] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [evaluatingId, setEvaluatingId] = useState(null)
  const [evaluateAllProgress, setEvaluateAllProgress] = useState(null)
  const [drawerEntity, setDrawerEntity] = useState(null)
  const [toast, setToast] = useState(null)

  const showToast = useCallback((message) => {
    setToast(message)
    window.setTimeout(() => setToast(null), 4000)
  }, [])

  const fetchScorecard = useCallback(
    async (entityId) => {
      const res = await authFetch(`/api/catalog/${encodeURIComponent(entityId)}/scorecard`)
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    },
    [authFetch]
  )

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await authFetch('/api/catalog')
      if (!res.ok) throw new Error(await res.text())
      const list = await res.json()
      const entityList = Array.isArray(list) ? list : []
      setEntities(entityList)

      const results = await Promise.all(
        entityList.map(async (entity) => {
          try {
            const data = await fetchScorecard(entity.id)
            return [entity.id, data]
          } catch {
            return [entity.id, { overall_score: 0, checks: [], by_category: [] }]
          }
        })
      )
      setCards(Object.fromEntries(results))
    } catch (e) {
      setError(e.message || 'Failed to load scorecards')
      setEntities([])
      setCards({})
    } finally {
      setLoading(false)
    }
  }, [authFetch, fetchScorecard])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  const evaluateEntity = useCallback(
    async (entity, { silent = false } = {}) => {
      setEvaluatingId(entity.id)
      try {
        const res = await authFetch(
          `/api/catalog/${encodeURIComponent(entity.id)}/scorecard/evaluate`,
          { method: 'POST' }
        )
        if (!res.ok) throw new Error(await res.text())
        const data = await res.json()
        setCards((prev) => ({ ...prev, [entity.id]: data }))
        if (!silent) showToast(`Scorecard updated for ${entity.name}`)
        return data
      } catch (e) {
        if (!silent) setError(e.message || 'Evaluation failed')
        throw e
      } finally {
        setEvaluatingId(null)
      }
    },
    [authFetch, showToast]
  )

  const evaluateAll = async () => {
    const list = entities.filter((e) => e.is_active !== 0)
    if (!list.length) return
    setEvaluateAllProgress({ done: 0, total: list.length })
    setError(null)
    const outcomes = []
    for (let i = 0; i < list.length; i += 1) {
      setEvaluateAllProgress({ done: i, total: list.length })
      try {
        const data = await evaluateEntity(list[i], { silent: true })
        outcomes.push([list[i].id, data])
      } catch {
        /* continue */
      }
      setEvaluateAllProgress({ done: i + 1, total: list.length })
    }
    setCards((prev) => {
      const next = { ...prev }
      for (const [id, data] of outcomes) next[id] = data
      return next
    })
    setEvaluateAllProgress(null)
    showToast(`Evaluated ${outcomes.length} of ${list.length} entities`)
  }

  const kpis = useMemo(() => {
    const evaluated = entities
      .map((e) => cards[e.id])
      .filter((sc) => sc && hasEvaluation(sc))
    const scores = evaluated.map((sc) => sc.overall_score ?? 0)
    return {
      totalScored: scores.length,
      avg: scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0,
      passing: scores.filter((s) => s >= 70).length,
      failing: scores.filter((s) => s < 50).length,
    }
  }, [entities, cards])

  const filteredEntities = useMemo(() => {
    const q = search.trim().toLowerCase()
    return entities.filter((entity) => {
      if (q && !(entity.name || '').toLowerCase().includes(q)) return false
      const sc = cards[entity.id]
      const score = sc?.overall_score ?? 0
      const evaluated = hasEvaluation(sc)
      if (filter === 'none') return !evaluated
      if (!evaluated) return false
      if (filter === 'passing') return score >= 70
      if (filter === 'warning') return score >= 50 && score < 70
      if (filter === 'failing') return score < 50
      return true
    })
  }, [entities, cards, search, filter])

  const drawerScorecard = drawerEntity ? cards[drawerEntity.id] : null
  const drawerGrouped = useMemo(() => {
    if (!drawerScorecard) return []
    if (drawerScorecard.by_category?.length) return drawerScorecard.by_category
    const byCat = {}
    for (const c of drawerScorecard.checks ?? []) {
      if (!byCat[c.category]) byCat[c.category] = []
      byCat[c.category].push(c)
    }
    return CATEGORIES.filter((cat) => byCat[cat]).map((category) => ({
      category,
      checks: byCat[category],
    }))
  }, [drawerScorecard])

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-16 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <ClipboardCheck className="w-5 h-5 text-indigo-400" />
            Scorecards
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Entity quality scores across the catalog</p>
        </div>
        <button
          type="button"
          onClick={() => void evaluateAll()}
          disabled={loading || !!evaluateAllProgress || entities.length === 0}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold disabled:opacity-50"
        >
          {evaluateAllProgress ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Evaluating {evaluateAllProgress.done} of {evaluateAllProgress.total}…
            </>
          ) : (
            <>
              <RefreshCw className="w-4 h-4" />
              Evaluate All
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => void loadAll()}
            className="px-3 py-1 rounded-lg border border-red-500/40 hover:bg-red-500/20 text-xs font-semibold"
          >
            Retry
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="Total Entities Scored" value={kpis.totalScored} border="border-indigo-500/20" />
        <KpiCard label="Avg Score" value={kpis.avg} border="border-sky-500/20" />
        <KpiCard label="Passing" value={kpis.passing} border="border-emerald-500/20" />
        <KpiCard label="Failing" value={kpis.failing} border="border-red-500/20" />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search entities…"
            className="w-full pl-9 pr-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white placeholder-slate-600"
          />
        </div>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="px-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
        >
          {FILTER_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {!loading && entities.length === 0 && (
        <div className="text-center py-16 rounded-2xl border border-border bg-card">
          <p className="text-slate-400">No entities in catalog yet</p>
          <Link
            to="/catalog"
            className="inline-block mt-3 text-sm font-semibold text-indigo-400 hover:text-indigo-300"
          >
            Go to Catalog
          </Link>
        </div>
      )}

      {!loading && entities.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredEntities.map((entity) => {
            const sc = cards[entity.id]
            const evaluated = hasEvaluation(sc)
            const score = sc?.overall_score ?? 0
            const scores = categoryScores(sc)
            const busy = evaluatingId === entity.id

            if (!evaluated) {
              return (
                <div
                  key={entity.id}
                  className="rounded-2xl border border-border bg-slate-900/40 p-5 flex flex-col items-center text-center gap-3 opacity-80"
                >
                  <div className="flex items-center gap-2 w-full justify-center flex-wrap">
                    <span className="font-semibold text-white">{entity.name}</span>
                    <KindBadge kind={entity.kind} />
                  </div>
                  <p className="text-sm text-slate-500">Not yet evaluated</p>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void evaluateEntity(entity)}
                    className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 disabled:opacity-50 inline-flex items-center gap-1"
                  >
                    {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                    Evaluate
                  </button>
                </div>
              )
            }

            return (
              <div
                key={entity.id}
                className="rounded-2xl border border-border bg-card p-5 flex flex-col gap-4"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-semibold text-white truncate">{entity.name}</p>
                    <KindBadge kind={entity.kind} />
                  </div>
                  <ScoreRing score={score} />
                </div>
                <CategoryBars scores={scores} />
                <div className="flex gap-2 mt-auto">
                  <button
                    type="button"
                    onClick={() => setDrawerEntity(entity)}
                    className="flex-1 py-2 rounded-lg border border-border text-xs font-semibold text-slate-300 hover:bg-slate-800"
                  >
                    View Details
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void evaluateEntity(entity)}
                    className="flex-1 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold disabled:opacity-50 inline-flex items-center justify-center gap-1"
                  >
                    {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                    Re-evaluate
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {!loading && entities.length > 0 && filteredEntities.length === 0 && (
        <p className="text-center text-slate-500 py-8">No entities match your search or filter.</p>
      )}

      {drawerEntity && (
        <>
          <button
            type="button"
            aria-label="Close drawer"
            className="fixed inset-0 z-[70] bg-black/60"
            onClick={() => setDrawerEntity(null)}
          />
          <aside className="fixed top-0 right-0 z-[80] h-full w-full max-w-md bg-slate-950 border-l border-border shadow-2xl flex flex-col overflow-hidden">
            <div className="flex items-start justify-between px-5 py-4 border-b border-border gap-3">
              <div>
                <h2 className="text-lg font-bold text-white">{drawerEntity.name}</h2>
                <div className="flex flex-wrap gap-2 mt-2">
                  <KindBadge kind={drawerEntity.kind} />
                  <LifecycleBadge lifecycle={drawerEntity.lifecycle} />
                </div>
              </div>
              <button
                type="button"
                onClick={() => setDrawerEntity(null)}
                className="p-2 rounded-lg hover:bg-slate-800 text-slate-400"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-6">
              <div className="flex justify-center mb-6">
                <ScoreRing score={drawerScorecard?.overall_score ?? 0} size={96} />
              </div>
              {drawerGrouped.length === 0 ? (
                <p className="text-center text-sm text-slate-500">No checks yet — run evaluation.</p>
              ) : (
                <div className="space-y-2">
                  {drawerGrouped.map(({ category, checks }) => (
                    <details
                      key={category}
                      className="rounded-xl border border-border bg-slate-900/50 overflow-hidden group"
                    >
                      <summary className="flex items-center justify-between cursor-pointer px-4 py-3 text-sm font-semibold text-slate-300 list-none">
                        <span>{category}</span>
                        <ChevronDown className="w-4 h-4 text-slate-500 group-open:rotate-180 transition-transform" />
                      </summary>
                      <div className="px-4 pb-3 space-y-3 border-t border-border/60">
                        {checks.map((check) => (
                          <div
                            key={`${category}-${check.check_name}`}
                            className="rounded-lg border border-border/60 bg-slate-950/80 p-3"
                          >
                            <div className="flex items-center gap-2 text-sm">
                              <CheckStatusDot status={check.status} />
                              <span className="flex-1 text-white font-medium">{check.check_name}</span>
                              <span className="text-slate-400 tabular-nums text-xs">
                                {check.score}/100
                              </span>
                              <span
                                className={`text-[10px] font-bold uppercase ${
                                  check.status === 'pass'
                                    ? 'text-emerald-400'
                                    : check.status === 'fail'
                                      ? 'text-red-400'
                                      : 'text-amber-400'
                                }`}
                              >
                                {statusLabel(check.status)}
                              </span>
                            </div>
                            {check.rationale && (
                              <p className="text-xs text-slate-500 mt-2 pl-4">{check.rationale}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    </details>
                  ))}
                </div>
              )}
            </div>
            <div className="px-5 py-4 border-t border-border">
              <button
                type="button"
                disabled={evaluatingId === drawerEntity.id}
                onClick={() => void evaluateEntity(drawerEntity)}
                className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold disabled:opacity-50 inline-flex items-center justify-center gap-2"
              >
                {evaluatingId === drawerEntity.id ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <RefreshCw className="w-4 h-4" />
                )}
                Re-evaluate
              </button>
            </div>
          </aside>
        </>
      )}

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[90] px-4 py-2.5 rounded-xl border border-emerald-500/40 bg-emerald-950/90 text-emerald-100 text-sm shadow-xl">
          {toast}
        </div>
      )}
    </div>
  )
}
