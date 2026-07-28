import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Plus,
  Edit2,
  Trash2,
  TestTube,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Settings,
  RefreshCw,
  Search,
  Filter,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const CATEGORIES = [
  { id: 'cloud', label: 'Cloud Providers', icon: '☁️' },
  { id: 'source_control', label: 'Source Control', icon: '🔁' },
  { id: 'project_mgmt', label: 'Project Management', icon: '📋' },
  { id: 'comms', label: 'Communication', icon: '💬' },
  { id: 'monitoring', label: 'Monitoring', icon: '📊' },
  { id: 'databases', label: 'Databases', icon: '🗄️' },
  { id: 'kubernetes', label: 'Kubernetes', icon: '🐳' },
  { id: 'secrets', label: 'Secrets Management', icon: '🔐' },
  { id: 'cicd', label: 'CI/CD', icon: '⚙️' },
]

const ENV_OPTIONS = [
  { value: 'local', label: 'Local' },
  { value: 'development', label: 'Development' },
  { value: 'test', label: 'Test' },
  { value: 'staging', label: 'Staging' },
  { value: 'production', label: 'Production' },
  { value: 'dr', label: 'DR' },
]

const MATRIX_COLS = ['Local', 'Development', 'Test', 'Staging', 'Production', 'DR']

const INSTANCE_URL_TOOLS = new Set([
  'jira',
  'gitlab',
  'grafana',
  'prometheus',
  'vault',
  'jenkins',
  'argocd',
  'github',
  'outbound_webhook',
  'servicenow',
])

const AUTH_LABELS = {
  iam_role: 'IAM Role (Recommended)',
  access_keys: 'Access Keys',
  sso: 'SSO',
  service_account: 'Service Account',
  workload_identity: 'Workload Identity',
  oauth2: 'OAuth2',
  client_secret: 'Client Secret',
  managed_identity: 'Managed Identity',
  certificate: 'Certificate',
  pat: 'Personal Access Token',
  github_app: 'GitHub App',
  api_token: 'API Token',
  basic: 'Basic Auth',
  bot_token: 'Bot Token',
  webhook: 'Webhook',
  api_key: 'API Key',
  user_token: 'User Token',
  api_key_app_key: 'API Key + App Key',
  bearer_token: 'Bearer Token',
  none: 'No Auth',
  kubeconfig: 'Kubeconfig File',
  oidc: 'OIDC',
  connection_string: 'Connection String',
  username_password: 'Username / Password',
  token: 'Token',
  approle: 'AppRole',
  kubernetes: 'Kubernetes Auth',
}

function authPlaceholder(authType) {
  const a = (authType || '').toLowerCase()
  if (a === 'iam_role') return 'arn:aws:iam::123456789012:role/PortalRole'
  if (a === 'pat' || a === 'api_token') return 'ghp_xxxxxxxxxxxxxxxxxxxx / API token'
  if (a === 'kubeconfig') return 'Paste kubeconfig YAML here'
  if (a === 'connection_string') return 'postgres://user:pass@host:5432/db'
  return 'Credentials or secret reference'
}

function identifierLabel(toolId) {
  const m = {
    aws: 'AWS Account ID',
    gcp: 'GCP Project ID',
    github: 'Org Name',
    jira: 'Email Address',
    kubernetes: 'Cluster Name',
  }
  return m[toolId] || 'Account Identifier'
}

function normalizeEnvLabel(env) {
  if (!env) return ''
  const e = env.toLowerCase()
  const hit = ENV_OPTIONS.find((o) => o.value === e)
  return hit ? hit.label : env
}

function envMatchesMatrixCol(accountEnv, colLabel) {
  const opt = ENV_OPTIONS.find((o) => o.label === colLabel)
  if (!opt) return false
  return (accountEnv || '').toLowerCase() === opt.value
}

function envBadgeClass(env) {
  const e = (env || '').toLowerCase()
  if (e === 'production') return 'bg-red-500/15 text-red-300 border-red-500/30'
  if (e === 'staging') return 'bg-yellow-500/15 text-yellow-200 border-yellow-500/30'
  if (e === 'dr') return 'bg-orange-500/15 text-orange-200 border-orange-500/30'
  return 'bg-blue-500/15 text-blue-200 border-blue-500/30'
}

function accountStatusBadge(status) {
  const s = (status || 'unknown').toLowerCase()
  if (s === 'connected')
    return { cls: 'bg-green-500/15 text-green-300 border-green-500/30', text: '✅ connected' }
  if (s === 'failed') return { cls: 'bg-red-500/15 text-red-300 border-red-500/30', text: '❌ failed' }
  if (s === 'expiring') return { cls: 'bg-orange-500/15 text-orange-200 border-orange-500/30', text: '⚠️ expiring' }
  return { cls: 'bg-slate-600/30 text-slate-400 border-slate-500/30', text: '⚪ unknown' }
}

function toolAggregateStatus(toolId, list) {
  if (!list || list.length === 0) return 'empty'
  if (list.some((a) => (a.status || '').toLowerCase() === 'failed')) return 'failed'
  if (list.some((a) => (a.status || '').toLowerCase() === 'unknown')) return 'degraded'
  if (list.every((a) => (a.status || '').toLowerCase() === 'connected')) return 'ok'
  return 'degraded'
}

function statusDotClass(agg) {
  if (agg === 'ok') return 'bg-green-500'
  if (agg === 'failed') return 'bg-red-500 animate-pulse'
  if (agg === 'degraded') return 'bg-yellow-400 animate-pulse'
  return 'bg-slate-500'
}

export default function ToolRegistryView() {
  const { authFetch } = useAuth()
  const { role } = useAuth()

  const [tools, setTools] = useState({})
  const [accounts, setAccounts] = useState({})
  const [expandedTools, setExpandedTools] = useState(() => new Set())
  const [expandedCats, setExpandedCats] = useState(() => new Set(CATEGORIES.map((c) => c.id)))
  const [selectedTool, setSelectedTool] = useState(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [editingAccount, setEditingAccount] = useState(null)
  const [isTestingConnection, setIsTestingConnection] = useState({})
  const [connectionResults, setConnectionResults] = useState({})
  const [githubRepos, setGithubRepos] = useState(null)
  const [githubReposError, setGithubReposError] = useState('')
  const [githubReposLoading, setGithubReposLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [filterCategory, setFilterCategory] = useState('all')
  const [filterStatus, setFilterStatus] = useState('all')
  const [matrixView, setMatrixView] = useState(false)
  const [toast, setToast] = useState(null)
  const [formError, setFormError] = useState('')
  const [authTypes, setAuthTypes] = useState([])
  const [saving, setSaving] = useState(false)

  const [formAccountName, setFormAccountName] = useState('')
  const [formEnvironment, setFormEnvironment] = useState('development')
  const [formRegion, setFormRegion] = useState('')
  const [formIdentifier, setFormIdentifier] = useState('')
  const [formInstanceUrl, setFormInstanceUrl] = useState('')
  const [formAuthType, setFormAuthType] = useState('')
  const [formCredentials, setFormCredentials] = useState('')
  const [showSecret, setShowSecret] = useState(false)
  const [formHitl, setFormHitl] = useState(false)
  const [formAssign, setFormAssign] = useState('all')

  const showToast = useCallback((msg) => {
    setToast(msg)
    window.setTimeout(() => setToast(null), 4000)
  }, [])

  const fetchTools = useCallback(async () => {
    try {
      const res = await authFetch('/api/tools')
      if (!res.ok) return
      const data = await res.json()
      setTools(typeof data === 'object' && data !== null ? data : {})
    } catch {
      setTools({})
    }
  }, [authFetch])

  const fetchAccounts = useCallback(
    async (toolId) => {
      try {
        const res = await authFetch(`/api/tools/${encodeURIComponent(toolId)}/accounts`)
        if (!res.ok) return
        const data = await res.json()
        setAccounts((prev) => ({ ...prev, [toolId]: Array.isArray(data) ? data : [] }))
      } catch {
        setAccounts((prev) => ({ ...prev, [toolId]: [] }))
      }
    },
    [authFetch]
  )

  useEffect(() => {
    if (role === 'Admin') fetchTools()
  }, [fetchTools, role])

  useEffect(() => {
    if (formEnvironment === 'production') setFormHitl(true)
  }, [formEnvironment])

  useEffect(() => {
    const tid = selectedTool?.id
    if (!tid || (!showAddForm && !editingAccount)) {
      setAuthTypes([])
      return undefined
    }
    let cancelled = false
    ;(async () => {
      try {
        const res = await authFetch(`/api/tools/${encodeURIComponent(tid)}/auth-types`)
        if (cancelled || !res.ok) return
        const list = await res.json()
        const arr = Array.isArray(list) ? list : []
        setAuthTypes(arr)
        if (showAddForm && !editingAccount && arr.length) {
          setFormAuthType((prev) => (prev && arr.includes(prev) ? prev : arr[0]))
        }
      } catch {
        if (!cancelled) setAuthTypes([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [authFetch, selectedTool?.id, showAddForm, editingAccount])

  const resetForm = useCallback(() => {
    setFormAccountName('')
    setFormEnvironment('development')
    setFormRegion('')
    setFormIdentifier('')
    setFormInstanceUrl('')
    setFormAuthType('')
    setFormCredentials('')
    setFormHitl(false)
    setFormAssign('all')
    setFormError('')
    setShowSecret(false)
  }, [])

  const openAddPanel = useCallback(
    (tool) => {
      setSelectedTool(tool)
      setEditingAccount(null)
      setShowAddForm(true)
      resetForm()
      setAuthTypes([])
    },
    [resetForm]
  )

  const openEditPanel = useCallback(
    (tool, acc) => {
      setSelectedTool(tool)
      setEditingAccount(acc)
      setShowAddForm(false)
      setFormAccountName(acc.account_name || '')
      setFormEnvironment((acc.environment || 'development').toLowerCase())
      setFormRegion(acc.region || '')
      setFormIdentifier(acc.account_identifier || '')
      setFormInstanceUrl(acc.instance_url || '')
      setFormAuthType(acc.auth_type || '')
      setFormCredentials('')
      setFormHitl(!!acc.requires_hitl)
      setFormError('')
    },
    []
  )

  const closePanel = useCallback(() => {
    setShowAddForm(false)
    setEditingAccount(null)
    setSelectedTool(null)
    resetForm()
  }, [resetForm])

  const toggleToolExpanded = useCallback(
    (toolId) => {
      setExpandedTools((prev) => {
        const next = new Set(prev)
        if (next.has(toolId)) next.delete(toolId)
        else {
          next.add(toolId)
          void fetchAccounts(toolId)
        }
        return next
      })
    },
    [fetchAccounts]
  )

  const toggleCatExpanded = useCallback((catId) => {
    setExpandedCats((prev) => {
      const next = new Set(prev)
      if (next.has(catId)) next.delete(catId)
      else next.add(catId)
      return next
    })
  }, [])

  const allToolsFlat = useMemo(() => {
    const out = []
    CATEGORIES.forEach((cat) => {
      const arr = tools[cat.id] || []
      arr.forEach((t) => out.push({ ...t, _category: cat.id }))
    })
    Object.keys(tools).forEach((k) => {
      if (CATEGORIES.some((c) => c.id === k)) return
      ;(tools[k] || []).forEach((t) => out.push({ ...t, _category: k }))
    })
    return out
  }, [tools])

  const filteredToolsForMatrix = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return allToolsFlat.filter((t) => {
      if (q && !(t.name || '').toLowerCase().includes(q)) return false
      if (filterCategory !== 'all' && t._category !== filterCategory) return false
      return true
    })
  }, [allToolsFlat, searchQuery, filterCategory])

  const fetchGithubRepos = useCallback(async () => {
    setGithubReposLoading(true)
    setGithubReposError('')
    try {
      const res = await authFetch('/api/github/repos?per_page=20')
      if (!res.ok) {
        const text = await res.text()
        let detail = text
        try {
          const j = JSON.parse(text)
          detail = j.detail || text
        } catch {
          /* keep text */
        }
        setGithubRepos([])
        setGithubReposError(typeof detail === 'string' ? detail : 'Failed to load repositories')
        return
      }
      const data = await res.json()
      setGithubRepos(Array.isArray(data) ? data : [])
    } catch (e) {
      setGithubRepos([])
      setGithubReposError(String(e?.message || e))
    } finally {
      setGithubReposLoading(false)
    }
  }, [authFetch])

  const runTest = useCallback(
    async (toolId, accountId) => {
      setIsTestingConnection((m) => ({ ...m, [accountId]: true }))
      setConnectionResults((r) => {
        const n = { ...r }
        delete n[accountId]
        return n
      })
      try {
        const res = await authFetch(
          `/api/tools/${encodeURIComponent(toolId)}/accounts/${encodeURIComponent(accountId)}/test`,
          { method: 'POST' }
        )
        const data = res.ok ? await res.json() : { connected: false, error: await res.text() }
        setConnectionResults((r) => ({ ...r, [accountId]: data }))
        void fetchAccounts(toolId)
        if (toolId === 'github' && data?.connected) {
          void fetchGithubRepos()
        }
      } catch (e) {
        setConnectionResults((r) => ({
          ...r,
          [accountId]: { connected: false, error: String(e?.message || e) },
        }))
      } finally {
        setIsTestingConnection((m) => ({ ...m, [accountId]: false }))
      }
    },
    [authFetch, fetchAccounts, fetchGithubRepos]
  )

  const saveAccount = useCallback(async () => {
    if (!selectedTool?.id) return
    if (!formAccountName.trim() || !formEnvironment || !formAuthType) {
      setFormError('Account name, environment, and auth method are required.')
      return
    }
    setSaving(true)
    setFormError('')
    const body = {
      account_name: formAccountName.trim(),
      environment: formEnvironment,
      region: formRegion.trim() || null,
      account_identifier: formIdentifier.trim() || null,
      instance_url: formInstanceUrl.trim() || null,
      auth_type: formAuthType,
      requires_hitl: formHitl ? 1 : 0,
    }
    if (formCredentials.trim()) {
      body.credentials_vault_ref = formCredentials.trim()
    }
    try {
      let res
      if (editingAccount?.id) {
        res = await authFetch(
          `/api/tools/${encodeURIComponent(selectedTool.id)}/accounts/${encodeURIComponent(editingAccount.id)}`,
          { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
        )
      } else {
        res = await authFetch(`/api/tools/${encodeURIComponent(selectedTool.id)}/accounts`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
      }
      if (!res.ok) {
        const t = await res.text()
        setFormError(t || 'Save failed')
        setSaving(false)
        return
      }
      showToast('Account saved successfully')
      closePanel()
      void fetchTools()
      void fetchAccounts(selectedTool.id)
    } catch (e) {
      setFormError(String(e?.message || e))
    } finally {
      setSaving(false)
    }
  }, [
    authFetch,
    closePanel,
    editingAccount,
    fetchAccounts,
    fetchTools,
    formAccountName,
    formAuthType,
    formCredentials,
    formEnvironment,
    formHitl,
    formIdentifier,
    formInstanceUrl,
    formRegion,
    selectedTool,
    showToast,
  ])

  const deleteAccount = useCallback(
    async (toolId, accountId) => {
      if (!window.confirm('Deactivate this account?')) return
      try {
        const res = await authFetch(
          `/api/tools/${encodeURIComponent(toolId)}/accounts/${encodeURIComponent(accountId)}`,
          { method: 'DELETE' }
        )
        if (res.ok) {
          showToast('Account deactivated')
          void fetchAccounts(toolId)
          void fetchTools()
        }
      } catch {
        /* noop */
      }
    },
    [authFetch, fetchAccounts, fetchTools, showToast]
  )

  const matrixCell = useCallback(
    (toolId, colLabel) => {
      const list = accounts[toolId] || []
      const acc = list.find(
        (a) => a.is_active !== false && envMatchesMatrixCol(a.environment, colLabel)
      )
      if (!acc) return { sym: '❌', title: 'Not configured', cls: 'text-slate-600' }
      const st = (acc.status || '').toLowerCase()
      if (st === 'connected') return { sym: '✅', title: acc.account_name, cls: 'text-green-400' }
      if (st === 'failed') return { sym: '⚠️', title: acc.account_name, cls: 'text-amber-400' }
      return { sym: '⚠️', title: acc.account_name, cls: 'text-yellow-400/90' }
    },
    [accounts]
  )

  if (role !== 'Admin') {
    return (
      <div className="max-w-md mx-auto mt-16 text-center text-slate-500 text-sm">
        Tool registry is restricted to Admins.
      </div>
    )
  }

  const panelOpen = showAddForm || editingAccount

  return (
    <div className="h-full min-h-[calc(100vh-8rem)] flex flex-col">
      {toast && (
        <div className="fixed bottom-6 right-6 z-[100] px-4 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}

      <div className="flex items-center justify-between gap-4 mb-6 shrink-0">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Settings className="w-6 h-6 text-accent" />
            Tool registry
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Manage integration accounts and connection tests</p>
        </div>
        <button
          type="button"
          onClick={() => setMatrixView((v) => !v)}
          className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${
            matrixView
              ? 'bg-accent/20 border-accent/40 text-accent'
              : 'bg-card border-border text-slate-300 hover:text-white'
          }`}
        >
          <span aria-hidden>📊</span>
          {matrixView ? 'Tree view' : 'Matrix view'}
        </button>
      </div>

      {matrixView ? (
        <div className="flex-1 overflow-auto rounded-xl border border-border bg-card/30">
          <table className="w-full text-xs text-left min-w-[720px]">
            <thead>
              <tr className="border-b border-border text-slate-500">
                <th className="p-3 font-medium sticky left-0 bg-card z-10">Tool</th>
                {MATRIX_COLS.map((c) => (
                  <th key={c} className="p-3 font-medium whitespace-nowrap">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredToolsForMatrix.map((tool) => (
                <tr key={tool.id} className="border-b border-border/60 hover:bg-card/40">
                  <td className="p-3 sticky left-0 bg-card/95 font-medium text-slate-200 whitespace-nowrap">
                    <span className="mr-1">{tool.icon}</span>
                    {tool.name}
                  </td>
                  {MATRIX_COLS.map((col) => {
                    const cell = matrixCell(tool.id, col)
                    return (
                      <td key={col} className={`p-3 text-center ${cell.cls}`} title={cell.title}>
                        {cell.sym}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-[minmax(0,30%)_minmax(0,70%)] gap-4 min-h-0">
          <div className="flex flex-col rounded-xl border border-border bg-card/40 overflow-hidden min-h-0">
            <div className="p-3 border-b border-border space-y-2 shrink-0">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input
                  className="w-full pl-9 pr-3 py-2 rounded-lg bg-slate-900/80 border border-border text-sm text-white placeholder:text-slate-600"
                  placeholder="Search tools..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              <div className="flex gap-2 items-center">
                <Filter className="w-3.5 h-3.5 text-slate-500 shrink-0" aria-hidden />
                <select
                  className="flex-1 text-xs rounded-lg bg-slate-900 border border-border px-2 py-1.5 text-slate-200"
                  value={filterCategory}
                  onChange={(e) => setFilterCategory(e.target.value)}
                >
                  <option value="all">All Categories</option>
                  {CATEGORIES.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label}
                    </option>
                  ))}
                </select>
                <select
                  className="flex-1 text-xs rounded-lg bg-slate-900 border border-border px-2 py-1.5 text-slate-200"
                  value={filterStatus}
                  onChange={(e) => setFilterStatus(e.target.value)}
                >
                  <option value="all">All Status</option>
                  <option value="connected">Connected</option>
                  <option value="failed">Failed</option>
                  <option value="unknown">Unknown</option>
                </select>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {CATEGORIES.filter((c) => filterCategory === 'all' || c.id === filterCategory).map((cat) => {
                const catTools = (tools[cat.id] || []).filter((t) =>
                  (t.name || '').toLowerCase().includes(searchQuery.trim().toLowerCase())
                )
                const catOpen = expandedCats.has(cat.id)
                return (
                  <div key={cat.id} className="rounded-lg border border-border/60 overflow-hidden">
                    <button
                      type="button"
                      className="w-full flex items-center gap-2 px-3 py-2.5 bg-slate-800/60 hover:bg-slate-800 text-left"
                      onClick={() => toggleCatExpanded(cat.id)}
                    >
                      {catOpen ? (
                        <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" />
                      )}
                      <span className="text-lg">{cat.icon}</span>
                      <span className="text-sm font-semibold text-white flex-1">{cat.label}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">
                        {catTools.length}
                      </span>
                    </button>
                    {catOpen && (
                      <div className="border-t border-border/40 bg-slate-900/40">
                        {catTools.length === 0 && (
                          <p className="text-xs text-slate-600 px-3 py-2">No tools in this category</p>
                        )}
                        {catTools.map((tool) => {
                          const tAccounts = accounts[tool.id] || []
                          const filteredAcc =
                            filterStatus === 'all'
                              ? tAccounts
                              : tAccounts.filter(
                                  (a) => (a.status || 'unknown').toLowerCase() === filterStatus
                                )
                          const agg = toolAggregateStatus(tool.id, tAccounts)
                          const expanded = expandedTools.has(tool.id)
                          const showAccounts = expanded && (filterStatus === 'all' ? tAccounts : filteredAcc)
                          return (
                            <div key={tool.id} className="border-b border-border/30 last:border-0">
                              <div className="flex items-center gap-2 px-2 py-2 pl-4">
                                <button
                                  type="button"
                                  className="p-0.5 text-slate-500 hover:text-white"
                                  onClick={() => toggleToolExpanded(tool.id)}
                                  aria-expanded={expanded}
                                >
                                  {expanded ? (
                                    <ChevronDown className="w-4 h-4" />
                                  ) : (
                                    <ChevronRight className="w-4 h-4" />
                                  )}
                                </button>
                                <span className="text-base">{tool.icon}</span>
                                <button
                                  type="button"
                                  className="flex-1 text-left text-sm text-slate-200 hover:text-white font-medium truncate"
                                  onClick={() => toggleToolExpanded(tool.id)}
                                >
                                  {tool.name}
                                </button>
                                <span
                                  className={`w-2 h-2 rounded-full shrink-0 ${statusDotClass(agg)}`}
                                  title={agg}
                                />
                                <span className="text-[10px] text-slate-500 tabular-nums">{tAccounts.length}</span>
                                <button
                                  type="button"
                                  className="p-1 rounded-md hover:bg-slate-700 text-accent"
                                  title="Add account"
                                  onClick={() => openAddPanel(tool)}
                                >
                                  <Plus className="w-4 h-4" />
                                </button>
                              </div>
                              {showAccounts && (
                                <div className="pl-8 pr-2 pb-2 space-y-1">
                                  {(filterStatus === 'all' ? tAccounts : filteredAcc).map((acc) => (
                                    <div
                                      key={acc.id}
                                      className="flex flex-wrap items-center gap-2 py-1.5 px-2 rounded-md bg-slate-800/50 border border-border/40"
                                    >
                                      <span className="text-xs text-slate-200 truncate flex-1 min-w-0">
                                        {acc.account_name}
                                      </span>
                                      <span
                                        className={`text-[10px] px-1.5 py-0.5 rounded border ${envBadgeClass(acc.environment)}`}
                                      >
                                        {normalizeEnvLabel(acc.environment)}
                                      </span>
                                      {(() => {
                                        const b = accountStatusBadge(acc.status)
                                        return (
                                          <span
                                            className={`text-[10px] px-1.5 py-0.5 rounded border capitalize ${b.cls}`}
                                          >
                                            {b.text}
                                          </span>
                                        )
                                      })()}
                                      <div className="flex items-center gap-0.5 ml-auto shrink-0">
                                        <button
                                          type="button"
                                          className="p-1 rounded hover:bg-slate-700 text-slate-400"
                                          title="Test"
                                          disabled={!!isTestingConnection[acc.id]}
                                          onClick={() => runTest(tool.id, acc.id)}
                                        >
                                          {isTestingConnection[acc.id] ? (
                                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                                          ) : (
                                            <TestTube className="w-3.5 h-3.5" />
                                          )}
                                        </button>
                                        <button
                                          type="button"
                                          className="p-1 rounded hover:bg-slate-700 text-slate-400"
                                          title="Edit"
                                          onClick={() => openEditPanel(tool, acc)}
                                        >
                                          <Edit2 className="w-3.5 h-3.5" />
                                        </button>
                                        <button
                                          type="button"
                                          className="p-1 rounded hover:bg-red-900/40 text-slate-400 hover:text-red-300"
                                          title="Delete"
                                          onClick={() => deleteAccount(tool.id, acc.id)}
                                        >
                                          <Trash2 className="w-3.5 h-3.5" />
                                        </button>
                                      </div>
                                      {connectionResults[acc.id] && (
                                        <div className="w-full mt-1 text-[10px]">
                                          {connectionResults[acc.id].connected ? (
                                            <div className="flex items-center gap-1 text-green-400 bg-green-500/10 border border-green-500/20 rounded px-2 py-1">
                                              <CheckCircle className="w-3 h-3" />
                                              Connected ({connectionResults[acc.id].latency_ms}ms)
                                            </div>
                                          ) : (
                                            <div className="flex items-start gap-1 text-red-300 bg-red-500/10 border border-red-500/20 rounded px-2 py-1">
                                              <XCircle className="w-3 h-3 shrink-0 mt-0.5" />
                                              Failed: {connectionResults[acc.id].error || 'Unknown'}
                                            </div>
                                          )}
                                        </div>
                                      )}
                                      {tool.id === 'github' &&
                                        connectionResults[acc.id]?.connected &&
                                        githubRepos !== null && (
                                          <div className="w-full mt-2 rounded-lg border border-slate-700/60 bg-slate-900/50 px-2 py-2">
                                            <p className="text-[10px] uppercase tracking-wide text-slate-500 mb-1.5">
                                              Repositories
                                            </p>
                                            {githubReposLoading ? (
                                              <p className="text-[10px] text-slate-500">Loading…</p>
                                            ) : githubReposError ? (
                                              <p className="text-[10px] text-amber-300">{githubReposError}</p>
                                            ) : githubRepos.length === 0 ? (
                                              <p className="text-[10px] text-slate-500">No repositories found.</p>
                                            ) : (
                                              <ul className="space-y-1 max-h-36 overflow-y-auto">
                                                {githubRepos.map((r) => (
                                                  <li key={r.id || r.full_name || r.name}>
                                                    {r.html_url ? (
                                                      <a
                                                        href={r.html_url}
                                                        target="_blank"
                                                        rel="noreferrer"
                                                        className="text-[11px] text-sky-300 hover:underline truncate block"
                                                      >
                                                        {r.full_name || r.name}
                                                      </a>
                                                    ) : (
                                                      <span className="text-[11px] text-slate-300">
                                                        {r.full_name || r.name}
                                                      </span>
                                                    )}
                                                  </li>
                                                ))}
                                              </ul>
                                            )}
                                          </div>
                                        )}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          <div className="rounded-xl border border-dashed border-border/60 bg-slate-900/20 min-h-[320px] flex flex-col">
            {!panelOpen && (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-600 text-sm p-8 text-center">
                <AlertTriangle className="w-10 h-10 mb-3 opacity-40" />
                <p>Select a tool and click [+] to add an account, or edit an existing account.</p>
              </div>
            )}
            {panelOpen && selectedTool && (
              <div className="flex flex-col h-full max-h-[calc(100vh-12rem)] overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
                  <div>
                    <h2 className="text-lg font-semibold text-white">
                      {editingAccount ? 'Edit Account' : 'Add Account'}
                    </h2>
                    <p className="text-xs text-slate-500 mt-0.5">
                      <span className="mr-1">{selectedTool.icon}</span>
                      {selectedTool.name}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={closePanel}
                    className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
                    aria-label="Close"
                  >
                    <XCircle className="w-5 h-5" />
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                  {formError && (
                    <div className="text-xs text-red-300 bg-red-500/10 border border-red-500/25 rounded-lg px-3 py-2">
                      {formError}
                    </div>
                  )}
                  <div>
                    <label className="block text-[10px] font-semibold text-slate-500 uppercase mb-1">
                      Account Name *
                    </label>
                    <input
                      className="w-full rounded-lg bg-slate-900 border border-border px-3 py-2 text-sm text-white"
                      placeholder="AWS Production US-East"
                      value={formAccountName}
                      onChange={(e) => setFormAccountName(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold text-slate-500 uppercase mb-1">
                      Environment *
                    </label>
                    <select
                      className="w-full rounded-lg bg-slate-900 border border-border px-3 py-2 text-sm text-white"
                      value={formEnvironment}
                      onChange={(e) => setFormEnvironment(e.target.value)}
                    >
                      {ENV_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold text-slate-500 uppercase mb-1">Region</label>
                    <input
                      className="w-full rounded-lg bg-slate-900 border border-border px-3 py-2 text-sm text-white"
                      placeholder="us-east-1"
                      value={formRegion}
                      onChange={(e) => setFormRegion(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold text-slate-500 uppercase mb-1">
                      {identifierLabel(selectedTool.id)}
                    </label>
                    <input
                      className="w-full rounded-lg bg-slate-900 border border-border px-3 py-2 text-sm text-white"
                      placeholder="Identifier"
                      value={formIdentifier}
                      onChange={(e) => setFormIdentifier(e.target.value)}
                    />
                  </div>
                  {INSTANCE_URL_TOOLS.has(selectedTool.id) && (
                    <div>
                      <label className="block text-[10px] font-semibold text-slate-500 uppercase mb-1">
                        Instance URL
                      </label>
                      <input
                        className="w-full rounded-lg bg-slate-900 border border-border px-3 py-2 text-sm text-white"
                        placeholder="https://your-org.atlassian.net"
                        value={formInstanceUrl}
                        onChange={(e) => setFormInstanceUrl(e.target.value)}
                      />
                    </div>
                  )}
                  <div>
                    <label className="block text-[10px] font-semibold text-slate-500 uppercase mb-1">
                      Auth Method *
                    </label>
                    <select
                      className="w-full rounded-lg bg-slate-900 border border-border px-3 py-2 text-sm text-white"
                      value={formAuthType}
                      onChange={(e) => setFormAuthType(e.target.value)}
                    >
                      {authTypes.map((a) => (
                        <option key={a} value={a}>
                          {AUTH_LABELS[a] || a}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-[10px] font-semibold text-slate-500 uppercase">
                        Credentials
                      </label>
                      <button
                        type="button"
                        className="text-[10px] text-accent"
                        onClick={() => setShowSecret((s) => !s)}
                      >
                        {showSecret ? 'Hide' : 'Show'}
                      </button>
                    </div>
                    {selectedTool?.id === 'github' && (
                      <p className="text-[10px] text-amber-200/90 mb-1.5 leading-snug">
                        Tokens are stored encrypted at rest. Use a fine-scoped PAT. Rotate if leaked.
                      </p>
                    )}
                    {editingAccount?.has_credentials && !formCredentials.trim() && (
                      <p className="text-[10px] text-slate-500 mb-1">
                        A credential is already saved. Leave blank to keep it, or paste a new token to rotate.
                      </p>
                    )}
                    <textarea
                      className="w-full rounded-lg bg-slate-900 border border-border px-3 py-2 text-sm text-white font-mono min-h-[88px]"
                      placeholder={
                        editingAccount?.has_credentials
                          ? '•••• saved — paste new token to rotate'
                          : authPlaceholder(formAuthType)
                      }
                      value={formCredentials}
                      onChange={(e) => setFormCredentials(e.target.value)}
                      autoComplete="off"
                      style={{ WebkitTextSecurity: showSecret ? 'none' : 'disc' }}
                    />
                  </div>
                  <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
                    <span className="text-xs text-slate-300">Require human approval for all actions</span>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={formHitl}
                      onClick={() => setFormHitl((v) => !v)}
                      className={`relative w-10 h-5 rounded-full transition-colors ${
                        formHitl ? 'bg-accent' : 'bg-slate-700'
                      }`}
                    >
                      <span
                        className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                          formHitl ? 'translate-x-5' : ''
                        }`}
                      />
                    </button>
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold text-slate-500 uppercase mb-2">Assign To</p>
                    <div className="flex flex-col gap-2 text-sm text-slate-300">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="assign"
                          checked={formAssign === 'all'}
                          onChange={() => setFormAssign('all')}
                        />
                        All Users
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="assign"
                          checked={formAssign === 'admin'}
                          onChange={() => setFormAssign('admin')}
                        />
                        Admin Only
                      </label>
                    </div>
                  </div>

                  {editingAccount?.id && (
                    <div className="pt-2 border-t border-border">
                      <button
                        type="button"
                        disabled={!!isTestingConnection[editingAccount.id]}
                        onClick={() => runTest(selectedTool.id, editingAccount.id)}
                        className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-sm text-slate-200 hover:bg-slate-800 w-full justify-center"
                      >
                        {isTestingConnection[editingAccount.id] ? (
                          <RefreshCw className="w-4 h-4 animate-spin" />
                        ) : (
                          <TestTube className="w-4 h-4" />
                        )}
                        Test Connection
                      </button>
                      {connectionResults[editingAccount.id] && (
                        <div className="mt-2 text-xs">
                          {connectionResults[editingAccount.id].connected ? (
                            <div className="flex items-center gap-2 text-green-400 bg-green-500/10 border border-green-500/25 rounded-lg px-3 py-2">
                              <CheckCircle className="w-4 h-4" />
                              Connected ({connectionResults[editingAccount.id].latency_ms}ms)
                            </div>
                          ) : (
                            <div className="flex items-start gap-2 text-red-300 bg-red-500/10 border border-red-500/25 rounded-lg px-3 py-2">
                              <XCircle className="w-4 h-4 shrink-0" />
                              Failed: {connectionResults[editingAccount.id].error || 'Error'}
                            </div>
                          )}
                        </div>
                      )}
                      {selectedTool?.id === 'github' &&
                        connectionResults[editingAccount.id]?.connected && (
                          <div className="mt-3 rounded-lg border border-slate-700/60 bg-slate-900/40 px-3 py-2">
                            <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">
                              Repositories
                            </p>
                            {githubReposLoading ? (
                              <p className="text-xs text-slate-500">Loading…</p>
                            ) : githubReposError ? (
                              <p className="text-xs text-amber-300">{githubReposError}</p>
                            ) : !githubRepos || githubRepos.length === 0 ? (
                              <p className="text-xs text-slate-500">No repositories found.</p>
                            ) : (
                              <ul className="space-y-1.5 max-h-48 overflow-y-auto">
                                {githubRepos.map((r) => (
                                  <li key={r.id || r.full_name || r.name}>
                                    {r.html_url ? (
                                      <a
                                        href={r.html_url}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="text-xs text-sky-300 hover:underline"
                                      >
                                        {r.full_name || r.name}
                                      </a>
                                    ) : (
                                      <span className="text-xs text-slate-300">
                                        {r.full_name || r.name}
                                      </span>
                                    )}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        )}
                    </div>
                  )}

                  <div className="flex flex-wrap gap-2 pt-2">
                    <button
                      type="button"
                      onClick={saveAccount}
                      disabled={saving}
                      className="px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:opacity-90 disabled:opacity-50"
                    >
                      {saving ? 'Saving…' : 'Save Account'}
                    </button>
                    <button
                      type="button"
                      onClick={closePanel}
                      className="px-4 py-2 rounded-lg border border-border text-sm text-slate-300 hover:bg-slate-800"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
