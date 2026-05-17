import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Play,
  RefreshCw,
  Loader2,
  Shield,
  Eye,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import {
  RunActionModal,
  LogsDrawer,
  STATUS_COLORS,
  ACTION_TYPE_COLORS,
} from './entityActionsShared'

function groupByKind(actions) {
  return actions.reduce((acc, action) => {
    const kind =
      !action.entity_kind || action.entity_kind === 'all' ? 'General' : action.entity_kind
    if (!acc[kind]) acc[kind] = []
    acc[kind].push(action)
    return acc
  }, {})
}

function ActionCard({ action, onRun }) {
  const typeClass = ACTION_TYPE_COLORS[action.action_type] || ACTION_TYPE_COLORS.manual
  const kindLabel =
    !action.entity_kind || action.entity_kind === 'all' ? 'All types' : action.entity_kind

  return (
    <div className="bg-[#0f0f1a] border border-white/10 rounded-xl p-4 hover:border-white/20 transition-all group">
      <div className="flex items-start justify-between gap-2">
        <h4 className="font-semibold text-white">{action.name}</h4>
        <span className={`px-2 py-0.5 rounded text-[10px] font-medium shrink-0 ${typeClass}`}>
          {action.action_type}
        </span>
      </div>
      <p className="text-gray-400 text-sm mt-1 line-clamp-2">{action.description || '—'}</p>
      <span className="inline-block mt-2 text-[10px] text-gray-500 bg-white/5 border border-white/10 px-2 py-0.5 rounded">
        {kindLabel}
      </span>
      {action.requires_approval && (
        <p className="flex items-center gap-1 text-xs text-amber-400 mt-2">
          <Shield size={12} /> Approval required
        </p>
      )}
      <button
        type="button"
        onClick={onRun}
        className="mt-4 w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-colors"
      >
        <Play size={14} /> Run Action
      </button>
    </div>
  )
}

export default function EntityActionsPage() {
  const { authFetch } = useAuth()
  const [actions, setActions] = useState([])
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [runsLoading, setRunsLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('actions')
  const [selectedAction, setSelectedAction] = useState(null)
  const [selectedRun, setSelectedRun] = useState(null)
  const [filterKind, setFilterKind] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')
  const [toast, setToast] = useState(null)

  const showToast = useCallback((message) => {
    setToast(message)
    window.setTimeout(() => setToast(null), 4000)
  }, [])

  const fetchActions = useCallback(async () => {
    try {
      const res = await authFetch('/api/entity-actions')
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setActions(Array.isArray(data) ? data : data.items || [])
    } catch (e) {
      setError(e.message || 'Failed to load actions')
      setActions([])
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  const fetchRuns = useCallback(async () => {
    try {
      const res = await authFetch('/api/entity-action-runs')
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setRuns(Array.isArray(data) ? data : data.items || [])
    } catch (e) {
      setError(e.message || 'Failed to load run history')
      setRuns([])
    } finally {
      setRunsLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    void fetchActions()
    void fetchRuns()
  }, [fetchActions, fetchRuns])

  const handleRefresh = async () => {
    setRefreshing(true)
    setLoading(true)
    setRunsLoading(true)
    setError(null)
    await Promise.all([fetchActions(), fetchRuns()])
    setRefreshing(false)
  }

  const filteredActions = useMemo(() => {
    const q = searchTerm.trim().toLowerCase()
    return actions.filter((a) => {
      if (filterKind !== 'all' && a.entity_kind !== 'all' && a.entity_kind !== filterKind) {
        return false
      }
      if (!q) return true
      return (
        (a.name || '').toLowerCase().includes(q) ||
        (a.description || '').toLowerCase().includes(q) ||
        (a.slug || '').toLowerCase().includes(q)
      )
    })
  }, [actions, filterKind, searchTerm])

  const groupedActions = useMemo(() => groupByKind(filteredActions), [filteredActions])

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white">
      <div className="bg-[#0f0f1a] border-b border-white/5 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-white">Entity Actions</h1>
            <p className="text-sm text-gray-400 mt-0.5">
              Run platform operations on catalog entities
            </p>
          </div>
          <button
            type="button"
            onClick={() => void handleRefresh()}
            className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-sm text-gray-300 transition-colors"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        <div className="flex gap-1 mt-4">
          {['actions', 'history'].map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              {tab === 'actions'
                ? `Actions (${actions.length})`
                : `Run History (${runs.length})`}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {activeTab === 'actions' && loading && (
        <div className="p-6 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              className="h-40 bg-white/5 rounded-xl animate-pulse border border-white/5"
            />
          ))}
        </div>
      )}

      {activeTab === 'actions' && !loading && (
        <div className="p-6">
          <div className="flex items-center gap-3 mb-6 flex-wrap">
            <input
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search actions..."
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 w-64 focus:outline-none focus:border-blue-500/50"
            />
            <select
              value={filterKind}
              onChange={(e) => setFilterKind(e.target.value)}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white"
            >
              <option value="all">All Entity Types</option>
              <option value="Service">Service</option>
              <option value="API">API</option>
              <option value="Component">Component</option>
              <option value="Library">Library</option>
              <option value="Database">Database</option>
            </select>
          </div>

          {Object.entries(groupedActions).map(([kind, kindActions]) => (
            <div key={kind} className="mb-8">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                {kind} Actions ({kindActions.length})
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {kindActions.map((action) => (
                  <ActionCard
                    key={action.id}
                    action={action}
                    onRun={() => setSelectedAction(action)}
                  />
                ))}
              </div>
            </div>
          ))}

          {actions.length === 0 && (
            <div className="flex flex-col items-center justify-center py-24">
              <Play size={40} className="text-gray-700 mb-4" />
              <p className="text-gray-500 font-medium">No actions defined yet</p>
              <p className="text-gray-600 text-sm mt-1">
                Actions will appear here once platform teams configure them
              </p>
            </div>
          )}

          {actions.length > 0 && filteredActions.length === 0 && (
            <p className="text-center text-gray-500 py-12">No actions match your filters.</p>
          )}
        </div>
      )}

      {activeTab === 'history' && (
        <div className="p-6">
          {runsLoading ? (
            <div className="flex justify-center py-16 text-gray-400 gap-2">
              <Loader2 className="w-6 h-6 animate-spin" /> Loading run history…
            </div>
          ) : (
            <div className="bg-[#0f0f1a] border border-white/10 rounded-xl overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/5">
                    <th className="text-left text-xs text-gray-500 font-medium px-4 py-3 uppercase tracking-wider">
                      Action
                    </th>
                    <th className="text-left text-xs text-gray-500 font-medium px-4 py-3 uppercase tracking-wider">
                      Entity
                    </th>
                    <th className="text-left text-xs text-gray-500 font-medium px-4 py-3 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="text-left text-xs text-gray-500 font-medium px-4 py-3 uppercase tracking-wider">
                      Requested By
                    </th>
                    <th className="text-left text-xs text-gray-500 font-medium px-4 py-3 uppercase tracking-wider">
                      Date
                    </th>
                    <th className="text-right text-xs text-gray-500 font-medium px-4 py-3 uppercase tracking-wider">
                      Logs
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr
                      key={run.id}
                      className="border-b border-white/5 hover:bg-white/[0.02] transition-colors"
                    >
                      <td className="px-4 py-3 text-sm text-white">
                        {run.action_name || `Action #${run.action_id}`}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400 font-mono text-xs">
                        {run.entity_id || '—'}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                            STATUS_COLORS[run.status] || STATUS_COLORS.pending
                          }`}
                        >
                          {run.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">{run.requested_by}</td>
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {run.created_at ? new Date(run.created_at).toLocaleString() : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => setSelectedRun(run)}
                          className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300 text-sm"
                        >
                          <Eye size={14} /> View Logs
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {runs.length === 0 && (
                <p className="text-center text-gray-500 py-12 text-sm">No action runs yet.</p>
              )}
            </div>
          )}
        </div>
      )}

      {selectedAction && (
        <RunActionModal
          action={selectedAction}
          onClose={() => setSelectedAction(null)}
          onSuccess={(run) => {
            setSelectedAction(null)
            void fetchRuns()
            showToast(
              run.status === 'pending'
                ? 'Action submitted for approval'
                : 'Action completed successfully'
            )
          }}
        />
      )}

      {selectedRun && <LogsDrawer run={selectedRun} onClose={() => setSelectedRun(null)} />}

      {toast && (
        <div className="fixed bottom-6 right-6 z-[60] px-4 py-3 rounded-lg bg-emerald-600 text-white text-sm font-medium shadow-lg">
          {toast}
        </div>
      )}
    </div>
  )
}
