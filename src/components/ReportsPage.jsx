import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart2,
  PieChart,
  Users,
  AlertTriangle,
  XCircle,
  RefreshCw,
  Coins,
  Zap,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { PageHeader, Card, StatCard, SectionHeader, EmptyState } from './ui'
import {
  budgetBarTone,
  budgetUsagePct,
  formatTokenCount,
  formatUsdCost,
} from '../utils/llmUsageFormat'

const KPI_CARDS = [
  { key: 'total', label: 'Total Entities', field: 'total_entities', icon: BarChart2, iconClass: 'bg-blue-500/15 text-blue-400' },
  { key: 'owner', label: 'Missing Owner', field: 'missing_owner', icon: AlertTriangle, iconClass: 'bg-amber-500/15 text-amber-400' },
  { key: 'health', label: 'Unknown Health', field: 'unknown_health', icon: XCircle, iconClass: 'bg-red-500/15 text-red-400' },
  { key: 'types', label: 'Entity Types', field: 'kind_count', icon: PieChart, iconClass: 'bg-purple-500/15 text-purple-400' },
]

function scoreColor(score) {
  if (score >= 80) return 'text-green-400'
  if (score >= 60) return 'text-blue-400'
  if (score >= 40) return 'text-amber-400'
  return 'text-red-400'
}

function barColor(score) {
  if (score >= 80) return '#22c55e'
  if (score >= 60) return '#3b82f6'
  if (score >= 40) return '#f59e0b'
  return '#ef4444'
}

function SectionSkeleton() {
  return <div className="h-40 bg-card rounded-xl animate-pulse border border-border" />
}

export default function ReportsPage() {
  const { authFetch } = useAuth()
  const navigate = useNavigate()

  const [catalogData, setCatalogData] = useState(null)
  const [scorecardsData, setScorecardsData] = useState(null)
  const [standardsData, setStandardsData] = useState(null)
  const [teamData, setTeamData] = useState(null)
  const [llmUsage, setLlmUsage] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [sortTeamBy, setSortTeamBy] = useState('services_owned')
  const [sortDir, setSortDir] = useState('desc')

  const loadReports = useCallback(async () => {
    setError(null)
    try {
      const [cRes, scRes, stRes, tRes, llmRes] = await Promise.all([
        authFetch('/api/reports/catalog-overview'),
        authFetch('/api/reports/scorecards-overview'),
        authFetch('/api/reports/standards-overview'),
        authFetch('/api/reports/team-overview'),
        authFetch('/api/reports/llm-usage?days=30'),
      ])
      if (!cRes.ok) throw new Error(await cRes.text())
      if (!scRes.ok) throw new Error(await scRes.text())
      if (!stRes.ok) throw new Error(await stRes.text())
      if (!tRes.ok) throw new Error(await tRes.text())
      const [c, sc, st, t] = await Promise.all([
        cRes.json(),
        scRes.json(),
        stRes.json(),
        tRes.json(),
      ])
      setCatalogData(c)
      setScorecardsData(sc)
      setStandardsData(st)
      setTeamData(t)
      if (llmRes.ok) {
        setLlmUsage(await llmRes.json())
      } else {
        setLlmUsage(null)
      }
    } catch (e) {
      setError(e.message || 'Failed to load reports')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [authFetch])

  useEffect(() => {
    void loadReports()
  }, [loadReports])

  const handleRefresh = () => {
    setRefreshing(true)
    setLoading(true)
    void loadReports()
  }

  const handleSort = (col) => {
    if (sortTeamBy === col) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      setSortTeamBy(col)
      setSortDir('desc')
    }
  }

  const sortedTeams = useMemo(() => {
    const list = [...(teamData?.teams || [])]
    return list.sort((a, b) => {
      const av = a[sortTeamBy]
      const bv = b[sortTeamBy]
      if (typeof av === 'string' && typeof bv === 'string') {
        return sortDir === 'desc' ? bv.localeCompare(av) : av.localeCompare(bv)
      }
      const an = Number(av) || 0
      const bn = Number(bv) || 0
      return sortDir === 'desc' ? bn - an : an - bn
    })
  }, [teamData, sortTeamBy, sortDir])

  const warnPct =
    standardsData && standardsData.total_evaluated > 0
      ? (standardsData.warnings / standardsData.total_evaluated) * 100
      : 0
  const failPct =
    standardsData && standardsData.total_evaluated > 0
      ? (standardsData.failed / standardsData.total_evaluated) * 100
      : 0

  const kindCount = Object.keys(catalogData?.by_kind || {}).length

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Engineering Reports"
        subtitle="Catalog, scorecards, standards, team metrics, and org LLM token cost"
        actions={(
          <button
            type="button"
            onClick={handleRefresh}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium border border-border rounded-lg hover:bg-card transition-colors text-slate-400 hover:text-white"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        )}
      />

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex flex-col gap-6">
          <SectionSkeleton />
          <SectionSkeleton />
          <SectionSkeleton />
          <SectionSkeleton />
        </div>
      ) : (
        <>
          <section className="flex flex-col gap-4">
            <SectionHeader title="Catalog Health" />
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {KPI_CARDS.map(({ key, label, field, icon: Icon, iconClass }) => {
                let value = catalogData?.[field]
                if (field === 'kind_count') value = kindCount
                return (
                  <StatCard
                    key={key}
                    icon={Icon}
                    iconClass={iconClass}
                    label={label}
                    value={value != null ? value : '—'}
                  />
                )
              })}
            </div>
            <Card title="Entities by Kind" padding="p-4">
              <div className="flex flex-wrap gap-2">
                {Object.entries(catalogData?.by_kind || {}).length === 0 ? (
                  <EmptyState title="No catalog entities yet" className="py-6 w-full" />
                ) : (
                  Object.entries(catalogData.by_kind).map(([kind, count]) => (
                    <span
                      key={kind}
                      className="px-3 py-1 bg-white/5 border border-border rounded-full text-sm text-white"
                    >
                      {kind}
                      <span className="ml-1.5 text-gray-400">{count}</span>
                    </span>
                  ))
                )}
              </div>
            </Card>
          </section>

          <section className="flex flex-col gap-4">
            <SectionHeader title="Scorecard Performance" />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card
                title="Team Avg Score"
                actions={
                  <span className="text-xs text-slate-500">
                    Overall: {scorecardsData?.avg_score ?? '—'}
                  </span>
                }
              >
                <div className="space-y-3">
                  {(scorecardsData?.by_team || []).map((t) => (
                    <div key={t.team}>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="text-gray-400 truncate max-w-[160px]">{t.team}</span>
                        <span className="text-white font-medium ml-2">{t.avg_score}</span>
                      </div>
                      <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{
                            width: `${Math.min(t.avg_score, 100)}%`,
                            backgroundColor: barColor(t.avg_score),
                          }}
                        />
                      </div>
                    </div>
                  ))}
                  {(scorecardsData?.by_team || []).length === 0 && (
                    <EmptyState title="No scorecard data yet" className="py-6" />
                  )}
                </div>
              </Card>

              <Card title="Lowest Scoring Services">
                <div className="space-y-2">
                  {(scorecardsData?.lowest_scoring_services || []).length === 0 ? (
                    <EmptyState title="No scorecard data yet" className="py-6" />
                  ) : (
                    scorecardsData.lowest_scoring_services.map((svc, i) => (
                      <div
                        key={svc.id}
                        role="button"
                        tabIndex={0}
                        onClick={() =>
                          navigate(
                            svc.id
                              ? `/catalog?entity=${encodeURIComponent(svc.id)}`
                              : '/catalog'
                          )
                        }
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            navigate(
                              svc.id
                                ? `/catalog?entity=${encodeURIComponent(svc.id)}`
                                : '/catalog'
                            )
                          }
                        }}
                        className="flex items-center justify-between py-2 px-1 -mx-1 rounded border-b border-border last:border-0 cursor-pointer hover:bg-card/80 transition-colors"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-xs text-gray-600 w-4">{i + 1}</span>
                          <span className="text-sm text-white truncate">{svc.name}</span>
                        </div>
                        <span className={`text-sm font-medium shrink-0 ${scoreColor(svc.score)}`}>
                          {svc.score}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </Card>
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <SectionHeader title="Standards Compliance" />
            {standardsData && (
              <p className="text-sm text-gray-400">
                <span className="text-white font-semibold">{standardsData.pass_rate_pct}%</span> of
                evaluated entities meet production readiness standards ({standardsData.passed}{' '}
                passed, {standardsData.failed} failed, {standardsData.warnings} warnings)
              </p>
            )}
            <div className="h-3 bg-white/5 rounded-full overflow-hidden flex">
              <div
                style={{ width: `${standardsData?.pass_rate_pct || 0}%` }}
                className="bg-green-500 transition-all duration-700"
              />
              <div style={{ width: `${warnPct}%` }} className="bg-yellow-500" />
              <div style={{ width: `${failPct}%` }} className="bg-red-500" />
            </div>
            <Card title="Compliance by Team">
              <div className="space-y-3">
                {(standardsData?.by_team || []).length === 0 ? (
                  <EmptyState title="No evaluations yet" className="py-6" />
                ) : (
                  standardsData.by_team.map((t) => {
                    const total = t.passed + t.failed + t.warnings
                    const passW = total > 0 ? (t.passed / total) * 100 : 0
                    const warnW = total > 0 ? (t.warnings / total) * 100 : 0
                    const failW = total > 0 ? (t.failed / total) * 100 : 0
                    return (
                      <div key={t.team}>
                        <div className="flex items-center justify-between text-xs mb-1">
                          <span className="text-gray-400">{t.team}</span>
                          <span className="text-white">{Math.round(t.pass_rate * 100)}%</span>
                        </div>
                        <div className="h-2 rounded-full overflow-hidden flex">
                          <div style={{ width: `${passW}%` }} className="bg-green-500" />
                          <div style={{ width: `${warnW}%` }} className="bg-yellow-500" />
                          <div style={{ width: `${failW}%` }} className="bg-red-500" />
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
              <div className="flex items-center gap-4 mt-4">
                {[
                  ['bg-green-500', 'Passed'],
                  ['bg-yellow-500', 'Warning'],
                  ['bg-red-500', 'Failed'],
                ].map(([cls, label]) => (
                  <div key={label} className="flex items-center gap-1.5 text-xs text-gray-400">
                    <div className={`w-2 h-2 rounded-full ${cls}`} />
                    {label}
                  </div>
                ))}
              </div>
            </Card>
          </section>

          <section className="flex flex-col gap-4">
            <SectionHeader title="Token Utilization" icon={Coins} />
            <p className="text-sm text-gray-400 -mt-2">
              Organization LLM API usage across all portal users (last {llmUsage?.days ?? 30} days).
              Cost is an estimate from model list prices, not a provider invoice.
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard
                icon={Zap}
                iconClass="bg-emerald-500/15 text-emerald-400"
                label="Total Tokens"
                value={llmUsage ? formatTokenCount(llmUsage.total_tokens) : '—'}
              />
              <StatCard
                icon={Coins}
                iconClass="bg-amber-500/15 text-amber-400"
                label="Est. Cost (USD)"
                value={
                  llmUsage
                    ? formatUsdCost(llmUsage.estimated_cost_usd)
                    : '—'
                }
              />
              <StatCard
                icon={BarChart2}
                iconClass="bg-blue-500/15 text-blue-400"
                label="API Calls"
                value={llmUsage ? formatTokenCount(llmUsage.calls) : '—'}
              />
              <StatCard
                icon={Users}
                iconClass="bg-violet-500/15 text-violet-400"
                label="Active Users"
                value={llmUsage ? (llmUsage.by_user || []).length : '—'}
              />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card title="Usage by User">
                {(llmUsage?.by_user || []).length === 0 ? (
                  <EmptyState title="No LLM usage recorded yet" className="py-6" />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="text-left text-xs text-gray-500 font-medium px-2 py-2">User</th>
                          <th className="text-right text-xs text-gray-500 font-medium px-2 py-2">Tokens</th>
                          <th className="text-right text-xs text-gray-500 font-medium px-2 py-2">Calls</th>
                          <th className="text-right text-xs text-gray-500 font-medium px-2 py-2">Est. $</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(llmUsage.by_user || []).slice(0, 12).map((u) => (
                          <tr key={u.user_id} className="border-b border-border last:border-0">
                            <td className="px-2 py-2 text-sm text-white truncate max-w-[160px]">{u.user_id}</td>
                            <td className="px-2 py-2 text-sm text-gray-300 text-right">
                              {formatTokenCount(u.tokens)}
                            </td>
                            <td className="px-2 py-2 text-sm text-gray-300 text-right">{u.calls}</td>
                            <td className="px-2 py-2 text-sm text-amber-300 text-right">
                              {formatUsdCost(u.estimated_cost_usd)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
              <Card title="Usage by Provider / Model">
                {(llmUsage?.by_model || []).length === 0 && (llmUsage?.by_provider || []).length === 0 ? (
                  <EmptyState title="No provider usage yet" className="py-6" />
                ) : (
                  <div className="space-y-4">
                    <div className="space-y-2">
                      {(llmUsage?.by_provider || []).map((p) => (
                        <div key={p.provider} className="flex items-center justify-between text-sm">
                          <span className="text-gray-400">{p.provider}</span>
                          <span className="text-white">
                            {formatTokenCount(p.tokens)} tok · {formatUsdCost(p.estimated_cost_usd)}
                          </span>
                        </div>
                      ))}
                    </div>
                    <div className="border-t border-border pt-3 space-y-2">
                      {(llmUsage?.by_model || []).slice(0, 8).map((m) => (
                        <div key={`${m.provider}-${m.model}`} className="flex items-center justify-between text-xs">
                          <span className="text-gray-500 truncate max-w-[200px]">
                            {m.model} <span className="text-gray-600">({m.provider})</span>
                          </span>
                          <span className="text-gray-300 shrink-0 ml-2">
                            {formatTokenCount(m.tokens)} · {formatUsdCost(m.estimated_cost_usd)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            </div>
            {(llmUsage?.budget || []).length > 0 && (
              <Card title="Monthly Token Budgets">
                <div className="space-y-3">
                  {llmUsage.budget.map((b) => {
                    const budget = Number(b.monthly_token_budget || 0)
                    const used = Number(b.tokens_used_this_month || 0)
                    const pct = budgetUsagePct(used, budget)
                    const tone = budgetBarTone(pct)
                    return (
                      <div key={b.config_id ?? `${b.provider}-${b.model}`}>
                        <div className="flex items-center justify-between text-xs mb-1">
                          <span className="text-gray-400">
                            {b.model} <span className="text-gray-600">({b.provider})</span>
                          </span>
                          <span className="text-white">
                            {formatTokenCount(used)} / {formatTokenCount(budget)} ({pct}%)
                          </span>
                        </div>
                        <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${
                              tone === 'critical'
                                ? 'bg-red-500'
                                : tone === 'warn'
                                  ? 'bg-amber-500'
                                  : 'bg-emerald-500'
                            }`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </Card>
            )}
          </section>

          <section className="flex flex-col gap-4">
            <SectionHeader title="Team Overview" icon={Users} />
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    {[
                      { key: 'name', label: 'Team' },
                      { key: 'services_owned', label: 'Services Owned' },
                      { key: 'avg_score', label: 'Avg Score' },
                      { key: 'readiness_pct', label: 'Readiness %' },
                      { key: 'open_actions', label: 'Open Actions' },
                    ].map((col) => (
                      <th
                        key={col.key}
                        onClick={() => handleSort(col.key)}
                        className="text-left text-xs text-gray-500 font-medium px-4 py-3 uppercase tracking-wider cursor-pointer hover:text-gray-300"
                      >
                        {col.label}
                        {sortTeamBy === col.key && (sortDir === 'desc' ? ' ↓' : ' ↑')}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedTeams.length === 0 ? (
                    <tr>
                      <td colSpan={5}>
                        <EmptyState title="No team data yet" className="py-8" />
                      </td>
                    </tr>
                  ) : (
                    sortedTeams.map((t) => (
                      <tr
                        key={t.name}
                        onClick={() => navigate('/catalog')}
                        className="border-b border-border cursor-pointer hover:bg-card/80 transition-colors"
                      >
                        <td className="px-4 py-3 text-sm font-medium text-white">{t.name}</td>
                        <td className="px-4 py-3 text-sm text-gray-300">{t.services_owned}</td>
                        <td className={`px-4 py-3 text-sm font-medium ${scoreColor(t.avg_score)}`}>
                          {t.avg_score}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-1.5 bg-white/10 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  t.readiness_pct >= 70
                                    ? 'bg-green-500'
                                    : t.readiness_pct >= 40
                                      ? 'bg-yellow-500'
                                      : 'bg-red-500'
                                }`}
                                style={{ width: `${t.readiness_pct}%` }}
                              />
                            </div>
                            <span className="text-sm text-gray-300">{t.readiness_pct}%</span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          {t.open_actions > 0 ? (
                            <span className="px-2 py-0.5 bg-yellow-500/20 text-yellow-300 text-xs rounded-full border border-yellow-500/30">
                              {t.open_actions}
                            </span>
                          ) : (
                            <span className="text-gray-600 text-sm">—</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
