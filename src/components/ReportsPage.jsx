import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart2,
  PieChart,
  Users,
  AlertTriangle,
  XCircle,
  RefreshCw,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const KPI_CARDS = [
  { key: 'total', label: 'Total Entities', field: 'total_entities', icon: BarChart2, iconClass: 'text-blue-400' },
  { key: 'owner', label: 'Missing Owner', field: 'missing_owner', icon: AlertTriangle, iconClass: 'text-amber-400' },
  { key: 'health', label: 'Unknown Health', field: 'unknown_health', icon: XCircle, iconClass: 'text-red-400' },
  { key: 'types', label: 'Entity Types', field: 'kind_count', icon: PieChart, iconClass: 'text-purple-400' },
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
  return <div className="h-40 bg-white/5 rounded-xl animate-pulse border border-white/5 mb-8" />
}

export default function ReportsPage() {
  const { authFetch } = useAuth()
  const navigate = useNavigate()

  const [catalogData, setCatalogData] = useState(null)
  const [scorecardsData, setScorecardsData] = useState(null)
  const [standardsData, setStandardsData] = useState(null)
  const [teamData, setTeamData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [sortTeamBy, setSortTeamBy] = useState('services_owned')
  const [sortDir, setSortDir] = useState('desc')

  const loadReports = useCallback(async () => {
    setError(null)
    try {
      const [cRes, scRes, stRes, tRes] = await Promise.all([
        authFetch('/api/reports/catalog-overview'),
        authFetch('/api/reports/scorecards-overview'),
        authFetch('/api/reports/standards-overview'),
        authFetch('/api/reports/team-overview'),
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
    <div className="min-h-screen bg-[#0a0a0f] text-white">
      <div className="bg-[#0f0f1a] border-b border-white/5 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white flex items-center gap-2">
            <BarChart2 className="w-6 h-6 text-blue-400" />
            Engineering Reports
          </h1>
          <p className="text-sm text-gray-400 mt-0.5">
            Aggregated catalog, scorecard, standards, and team metrics
          </p>
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-sm text-gray-300"
        >
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      <div className="p-6 max-w-6xl mx-auto">
        {error && (
          <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        {loading ? (
          <>
            <SectionSkeleton />
            <SectionSkeleton />
            <SectionSkeleton />
            <SectionSkeleton />
          </>
        ) : (
          <>
            <section className="mb-8">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">
                Catalog Health
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                {KPI_CARDS.map(({ key, label, field, icon: Icon, iconClass }) => {
                  let value = catalogData?.[field]
                  if (field === 'kind_count') value = kindCount
                  return (
                    <div
                      key={key}
                      className="bg-[#0f0f1a] border border-white/10 rounded-xl p-4"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <p className="text-xs text-gray-500">{label}</p>
                        <Icon size={14} className={iconClass} />
                      </div>
                      <p className="text-2xl font-bold text-white">
                        {value != null ? (
                          value
                        ) : (
                          <span className="text-gray-600 text-sm">—</span>
                        )}
                      </p>
                    </div>
                  )
                })}
              </div>
              <div className="bg-[#0f0f1a] border border-white/10 rounded-xl p-4">
                <p className="text-xs text-gray-500 mb-3">Entities by Kind</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(catalogData?.by_kind || {}).length === 0 ? (
                    <p className="text-gray-600 text-sm">No catalog entities yet</p>
                  ) : (
                    Object.entries(catalogData.by_kind).map(([kind, count]) => (
                      <span
                        key={kind}
                        className="px-3 py-1 bg-white/5 border border-white/10 rounded-full text-sm text-white"
                      >
                        {kind}
                        <span className="ml-1.5 text-gray-400">{count}</span>
                      </span>
                    ))
                  )}
                </div>
              </div>
            </section>

            <section className="mb-8">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">
                Scorecard Performance
              </h2>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="bg-[#0f0f1a] border border-white/10 rounded-xl p-5">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-sm font-medium text-white">Team Avg Score</p>
                    <p className="text-xs text-gray-500">
                      Overall: {scorecardsData?.avg_score ?? '—'}
                    </p>
                  </div>
                  <div className="space-y-3 mt-4">
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
                      <p className="text-gray-600 text-sm text-center py-4">No scorecard data yet</p>
                    )}
                  </div>
                </div>

                <div className="bg-[#0f0f1a] border border-white/10 rounded-xl p-5">
                  <p className="text-sm font-medium text-white mb-4">Lowest Scoring Services</p>
                  <div className="space-y-2">
                    {(scorecardsData?.lowest_scoring_services || []).length === 0 ? (
                      <p className="text-gray-600 text-sm text-center py-4">No scorecard data yet</p>
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
                          className="flex items-center justify-between py-2 px-1 -mx-1 rounded border-b border-white/5 last:border-0 cursor-pointer hover:bg-neutral-800 transition-colors"
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
                </div>
              </div>
            </section>

            <section className="mb-8">
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">
                Standards Compliance
              </h2>
              {standardsData && (
                <p className="text-sm text-gray-400 mb-4">
                  <span className="text-white font-semibold">{standardsData.pass_rate_pct}%</span> of
                  evaluated entities meet production readiness standards ({standardsData.passed}{' '}
                  passed, {standardsData.failed} failed, {standardsData.warnings} warnings)
                </p>
              )}
              <div className="h-3 bg-white/5 rounded-full overflow-hidden flex mb-6">
                <div
                  style={{ width: `${standardsData?.pass_rate_pct || 0}%` }}
                  className="bg-green-500 transition-all duration-700"
                />
                <div style={{ width: `${warnPct}%` }} className="bg-yellow-500" />
                <div style={{ width: `${failPct}%` }} className="bg-red-500" />
              </div>
              <div className="bg-[#0f0f1a] border border-white/10 rounded-xl p-5">
                <p className="text-sm font-medium text-white mb-4">Compliance by Team</p>
                <div className="space-y-3">
                  {(standardsData?.by_team || []).length === 0 ? (
                    <p className="text-gray-600 text-sm text-center py-4">No evaluations yet</p>
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
              </div>
            </section>

            <section>
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
                <Users size={16} /> Team Overview
              </h2>
              <div className="bg-[#0f0f1a] border border-white/10 rounded-xl overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-white/5">
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
                        <td colSpan={5} className="px-4 py-8 text-center text-gray-500 text-sm">
                          No team data yet
                        </td>
                      </tr>
                    ) : (
                      sortedTeams.map((t) => (
                        <tr
                          key={t.name}
                          onClick={() => navigate('/catalog')}
                          className="border-b border-white/5 cursor-pointer hover:bg-neutral-800 transition-colors"
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
    </div>
  )
}
