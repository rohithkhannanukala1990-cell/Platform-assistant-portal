import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ShieldCheck,
  AlertTriangle,
  XCircle,
  CheckCircle2,
  Loader2,
  RefreshCw,
} from 'lucide-react'
import { API_BASE } from '../config/apiBase'

function authHeaders(extra = {}) {
  const token = localStorage.getItem('token') || localStorage.getItem('aiops_access_token')
  const headers = { ...extra }
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

async function apiFetch(path, options = {}) {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const res = await fetch(url, {
    ...options,
    headers: authHeaders(options.headers || {}),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `Request failed (${res.status})`)
  }
  return res.json()
}

function statusPill(status) {
  if (status === 'pass') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
        <CheckCircle2 className="w-3 h-3" /> pass
      </span>
    )
  }
  if (status === 'warn') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
        <AlertTriangle className="w-3 h-3" /> warn
      </span>
    )
  }
  if (status === 'fail') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-red-500/15 text-red-400 border border-red-500/30">
        <XCircle className="w-3 h-3" /> fail
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-700/50 text-slate-400 border border-border">
      unknown
    </span>
  )
}

function scoreBar(score) {
  const pct = Math.max(0, Math.min(100, Number(score) || 0))
  const color = pct >= 80 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2 min-w-[100px]">
      <span className="text-sm font-semibold text-white tabular-nums w-8">{pct}</span>
      <div className="flex-1 h-1.5 rounded-full bg-slate-800 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function pickPrimaryEvaluation(evaluations, preferredSlug = 'prod-readiness-v1') {
  if (!Array.isArray(evaluations) || evaluations.length === 0) return null
  return (
    evaluations.find((e) => e.standard_slug === preferredSlug) ||
    evaluations[0]
  )
}

export default function StandardsPage() {
  const [standards, setStandards] = useState([])
  const [entities, setEntities] = useState([])
  const [evaluationsByEntity, setEvaluationsByEntity] = useState({})
  const [loading, setLoading] = useState(true)
  const [tableLoading, setTableLoading] = useState(false)
  const [error, setError] = useState(null)
  const [evaluatingStandardId, setEvaluatingStandardId] = useState(null)
  const [reevaluatingEntityId, setReevaluatingEntityId] = useState(null)

  const loadEvaluations = useCallback(async (entityList) => {
    const map = {}
    await Promise.all(
      entityList.map(async (entity) => {
        try {
          const evs = await apiFetch(`/api/catalog/${encodeURIComponent(entity.id)}/standards`)
          map[entity.id] = Array.isArray(evs) ? evs : []
        } catch {
          map[entity.id] = []
        }
      })
    )
    setEvaluationsByEntity(map)
  }, [])

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [stdList, catalog] = await Promise.all([
        apiFetch('/api/standards'),
        apiFetch('/api/catalog'),
      ])
      setStandards(Array.isArray(stdList) ? stdList : [])
      const list = Array.isArray(catalog) ? catalog : []
      setEntities(list)
      setTableLoading(true)
      await loadEvaluations(list)
    } catch (e) {
      setError(e.message || 'Failed to load standards data')
    } finally {
      setLoading(false)
      setTableLoading(false)
    }
  }, [loadEvaluations])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  const summary = useMemo(() => {
    let passing = 0
    let attention = 0
    let failing = 0
    for (const entity of entities) {
      const ev = pickPrimaryEvaluation(evaluationsByEntity[entity.id])
      const score = ev?.overall_score ?? null
      if (score === null || ev?.status === 'unknown') continue
      if (score >= 80) passing += 1
      else if (score >= 50) attention += 1
      else failing += 1
    }
    return {
      total: entities.length,
      passing,
      attention,
      failing,
    }
  }, [entities, evaluationsByEntity])

  const evaluateAllForStandard = async (standardId) => {
    if (!standardId || entities.length === 0) return
    setEvaluatingStandardId(standardId)
    setError(null)
    try {
      for (const entity of entities) {
        await apiFetch(
          `/api/catalog/${encodeURIComponent(entity.id)}/standards/${encodeURIComponent(standardId)}/evaluate`,
          { method: 'POST' }
        )
      }
      await loadEvaluations(entities)
    } catch (e) {
      setError(e.message || 'Bulk evaluation failed')
    } finally {
      setEvaluatingStandardId(null)
    }
  }

  const reevaluateEntity = async (entityId, standardId) => {
    if (!entityId || !standardId) return
    setReevaluatingEntityId(entityId)
    setError(null)
    try {
      await apiFetch(
        `/api/catalog/${encodeURIComponent(entityId)}/standards/${encodeURIComponent(standardId)}/evaluate`,
        { method: 'POST' }
      )
      const evs = await apiFetch(`/api/catalog/${encodeURIComponent(entityId)}/standards`)
      setEvaluationsByEntity((prev) => ({ ...prev, [entityId]: Array.isArray(evs) ? evs : [] }))
    } catch (e) {
      setError(e.message || 'Re-evaluation failed')
    } finally {
      setReevaluatingEntityId(null)
    }
  }

  const defaultStandardId =
    standards.find((s) => s.slug === 'prod-readiness-v1')?.id || standards[0]?.id

  return (
    <div className="max-w-7xl mx-auto w-full space-y-6 pb-16">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
          <ShieldCheck className="w-7 h-7 text-indigo-400" />
          Production Readiness Standards
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Evaluate catalog entities against platform compliance standards
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-950/30 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Total entities', value: summary.total, icon: ShieldCheck, cls: 'text-indigo-400 border-indigo-500/25 bg-indigo-500/5' },
          { label: 'Passing', value: summary.passing, icon: CheckCircle2, cls: 'text-emerald-400 border-emerald-500/25 bg-emerald-500/5' },
          { label: 'Needs attention', value: summary.attention, icon: AlertTriangle, cls: 'text-amber-400 border-amber-500/25 bg-amber-500/5' },
          { label: 'Failing', value: summary.failing, icon: XCircle, cls: 'text-red-400 border-red-500/25 bg-red-500/5' },
        ].map(({ label, value, icon: Icon, cls }) => (
          <div key={label} className={`rounded-xl border p-4 ${cls}`}>
            <div className="flex items-center gap-2 mb-2">
              <Icon className="w-4 h-4" />
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</span>
            </div>
            <p className="text-3xl font-bold text-white">{value}</p>
          </div>
        ))}
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider">Standards</h2>
        {loading ? (
          <div className="flex items-center justify-center py-12 text-slate-400 gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> Loading standards…
          </div>
        ) : standards.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border py-12 text-center text-slate-500">
            No standards defined yet.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {standards.map((std) => (
              <div
                key={std.id}
                className="rounded-xl border border-border bg-slate-900/50 p-4 flex flex-col gap-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-bold text-white">{std.name}</p>
                    <p className="text-xs text-slate-500 mt-0.5">v{std.version}</p>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-800 text-slate-300 border border-border">
                    {std.applies_to_kind}
                  </span>
                </div>
                <p className="text-sm text-slate-400 line-clamp-2">{std.description || '—'}</p>
                <p className="text-xs text-slate-500">{std.check_count ?? 0} checks</p>
                <button
                  type="button"
                  disabled={evaluatingStandardId === std.id || entities.length === 0}
                  onClick={() => void evaluateAllForStandard(std.id)}
                  className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold disabled:opacity-50"
                >
                  {evaluatingStandardId === std.id ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" /> Evaluating…
                    </>
                  ) : (
                    <>
                      <RefreshCw className="w-4 h-4" /> Evaluate All Services
                    </>
                  )}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider">Entity compliance</h2>
        {tableLoading ? (
          <div className="flex items-center justify-center py-16 text-slate-400 gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> Loading compliance data…
          </div>
        ) : entities.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border py-16 text-center text-slate-500">
            No catalog entities found.
          </div>
        ) : (
          <div className="rounded-xl border border-border overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-slate-900/80 text-left text-xs uppercase tracking-wider text-slate-500">
                    <th className="px-4 py-3 font-semibold">Entity</th>
                    <th className="px-4 py-3 font-semibold">Kind</th>
                    <th className="px-4 py-3 font-semibold">Owner team</th>
                    <th className="px-4 py-3 font-semibold">Score</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {entities.map((entity) => {
                    const ev = pickPrimaryEvaluation(evaluationsByEntity[entity.id])
                    const score = ev?.overall_score ?? 0
                    const status = ev?.status ?? 'unknown'
                    const standardId = ev?.standard_id || defaultStandardId
                    return (
                      <tr key={entity.id} className="border-b border-border/60 hover:bg-slate-900/40">
                        <td className="px-4 py-3 font-medium text-white">{entity.name}</td>
                        <td className="px-4 py-3 text-slate-400">{entity.kind}</td>
                        <td className="px-4 py-3 text-slate-400">{entity.owner_team}</td>
                        <td className="px-4 py-3">{scoreBar(score)}</td>
                        <td className="px-4 py-3">{statusPill(status)}</td>
                        <td className="px-4 py-3 text-right">
                          <button
                            type="button"
                            disabled={!standardId || reevaluatingEntityId === entity.id}
                            onClick={() => void reevaluateEntity(entity.id, standardId)}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                          >
                            {reevaluatingEntityId === entity.id ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <RefreshCw className="w-3.5 h-3.5" />
                            )}
                            Re-evaluate
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
