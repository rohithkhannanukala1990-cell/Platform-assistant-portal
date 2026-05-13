import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import {
  Upload,
  Download,
  Search,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Cloud,
  Github,
  Database,
  ChevronRight,
  FileText,
  Clock,
  Eye,
  Plus,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { PermissionGate } from './PermissionGate'

const AWS_REGION_OPTIONS = [
  { id: 'us-east-1', label: 'us-east-1' },
  { id: 'us-west-2', label: 'us-west-2' },
  { id: 'eu-west-1', label: 'eu-west-1' },
  { id: 'ap-southeast-1', label: 'ap-southeast-1' },
  { id: 'ap-northeast-1', label: 'ap-northeast-1' },
]

const JSON_EXAMPLE = `{
  "accounts": [
    {
      "tool_id": "aws",
      "account_name": "AWS Production",
      "environment": "production",
      "region": "us-east-1",
      "auth_type": "iam_role"
    }
  ]
}`

const TOOL_META = {
  aws: { emoji: '☁️', label: 'AWS' },
  gcp: { emoji: '🌐', label: 'GCP' },
  azure: { emoji: '🔷', label: 'Azure' },
  github: { emoji: '🐙', label: 'GitHub' },
  gitlab: { emoji: '🦊', label: 'GitLab' },
  jira: { emoji: '📋', label: 'Jira' },
  slack: { emoji: '💬', label: 'Slack' },
  kubernetes: { emoji: '☸️', label: 'Kubernetes' },
  datadog: { emoji: '🐶', label: 'Datadog' },
  pagerduty: { emoji: '🚨', label: 'PagerDuty' },
  default: { emoji: '🔧', label: 'Tool' },
}

function toolMeta(toolId) {
  const k = (toolId || '').toLowerCase()
  return TOOL_META[k] || { ...TOOL_META.default, label: toolId || 'Tool' }
}

function formatRelativeTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const sec = Math.floor((Date.now() - d.getTime()) / 1000)
  if (sec < 45) return 'just now'
  if (sec < 3600) return `${Math.floor(sec / 60)} min ago`
  if (sec < 86400) return `${Math.floor(sec / 3600)} hours ago`
  if (sec < 604800) return `${Math.floor(sec / 86400)} days ago`
  return d.toLocaleString()
}

function historyTypeLabel(importType) {
  const t = (importType || '').toLowerCase()
  if (t === 'csv') return 'CSV'
  if (t === 'json') return 'JSON'
  if (t === 'cloud_discover') return 'Cloud Discovery'
  if (t === 'service_discovery') return 'Service Discovery'
  return importType || '—'
}

function historyStatusRow(h) {
  const failed = h.failed ?? 0
  const imported = h.imported ?? 0
  if (failed > 0 && imported === 0) return { label: 'Failed', tone: 'fail' }
  if (failed > 0) return { label: 'Partial', tone: 'partial' }
  return { label: 'Complete', tone: 'ok' }
}

function envBadgeClass(env) {
  const e = (env || '').toLowerCase()
  if (e === 'production' || e === 'dr') return 'bg-rose-500/15 text-rose-200 border-rose-500/30'
  if (e === 'staging') return 'bg-amber-500/15 text-amber-200 border-amber-500/30'
  if (e === 'test') return 'bg-sky-500/15 text-sky-200 border-sky-500/30'
  return 'bg-slate-500/15 text-slate-200 border-slate-500/30'
}

export default function AccountImportView() {
  const { authFetch } = useAuth()

  const [activeTab, setActiveTab] = useState('upload')
  const [uploadType, setUploadType] = useState('csv')
  const [fileContent, setFileContent] = useState('')
  const [fileName, setFileName] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const [parseResult, setParseResult] = useState(null)
  const [selectedRows, setSelectedRows] = useState(() => new Set())
  const [isImporting, setIsImporting] = useState(false)
  const [importProgress, setImportProgress] = useState('')
  const [importResult, setImportResult] = useState(null)
  const [showJsonExample, setShowJsonExample] = useState(false)
  const [parseErrorsOpen, setParseErrorsOpen] = useState(true)

  const [discoverResult, setDiscoverResult] = useState(null)
  const [discoverKind, setDiscoverKind] = useState(null)
  const [isDiscovering, setIsDiscovering] = useState(false)
  const [discoverProvider, setDiscoverProvider] = useState('aws')
  const [selectedDiscoverIds, setSelectedDiscoverIds] = useState(() => new Set())

  const [awsAccountId, setAwsAccountId] = useState('')
  const [awsRegions, setAwsRegions] = useState(() => new Set(['us-east-1', 'us-west-2']))
  const [gcpProjectId, setGcpProjectId] = useState('')
  const [azureSubId, setAzureSubId] = useState('')
  const [azureTenantId, setAzureTenantId] = useState('')
  const [githubOrg, setGithubOrg] = useState('')

  const [historyItems, setHistoryItems] = useState([])
  const [historyPage, setHistoryPage] = useState(1)
  const [historyLoading, setHistoryLoading] = useState(false)

  const fileInputRef = useRef(null)

  const previewRows = useMemo(() => {
    const rows = parseResult?.rows || []
    return rows.slice(0, 10)
  }, [parseResult])

  const allRowIds = useMemo(() => {
    const rows = parseResult?.rows || []
    return rows.map((r) => r.id).filter(Boolean)
  }, [parseResult])

  useEffect(() => {
    if (!parseResult?.rows?.length) {
      setSelectedRows(new Set())
      return
    }
    setSelectedRows(new Set(parseResult.rows.map((r) => r.id).filter(Boolean)))
  }, [parseResult])

  const selectedRowObjects = useMemo(() => {
    const rows = parseResult?.rows || []
    return rows.filter((r) => r.id && selectedRows.has(r.id))
  }, [parseResult, selectedRows])

  const discoverRows = useMemo(() => {
    if (!discoverResult) return []
    return discoverResult.rows || discoverResult.accounts || []
  }, [discoverResult])

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const res = await authFetch('/api/import/history')
      if (!res.ok) throw new Error('history failed')
      const data = await res.json()
      setHistoryItems(Array.isArray(data) ? data : [])
    } catch {
      setHistoryItems([])
    } finally {
      setHistoryLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    if (activeTab === 'history') void loadHistory()
  }, [activeTab, loadHistory])

  const historyPageSlice = useMemo(() => {
    const start = (historyPage - 1) * 20
    return historyItems.slice(start, start + 20)
  }, [historyItems, historyPage])
  const historyTotalPages = Math.max(1, Math.ceil(historyItems.length / 20))

  const onDragOver = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }, [])
  const onDragLeave = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }, [])

  const ingestFile = useCallback((file) => {
    if (!file) return
    const ext = (file.name.split('.').pop() || '').toLowerCase()
    if (uploadType === 'csv' && ext !== 'csv') {
      window.alert('Please choose a .csv file for CSV mode.')
      return
    }
    if (uploadType === 'json' && ext !== 'json') {
      window.alert('Please choose a .json file for JSON mode.')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      setFileContent(typeof reader.result === 'string' ? reader.result : '')
      setFileName(file.name)
      setParseResult(null)
      setImportResult(null)
    }
    reader.readAsText(file)
  }, [uploadType])

  const onDrop = useCallback(
    (e) => {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(false)
      const f = e.dataTransfer?.files?.[0]
      if (f) ingestFile(f)
    },
    [ingestFile]
  )

  const downloadTemplate = useCallback(async () => {
    try {
      const res = await authFetch('/api/import/template/csv')
      if (!res.ok) throw new Error('template')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'accounts-template.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      window.alert('Could not download template.')
    }
  }, [authFetch])

  const runParse = useCallback(async () => {
    if (!fileContent.trim()) return
    setImportResult(null)
    try {
      if (uploadType === 'csv') {
        const blob = new Blob([fileContent], { type: 'text/csv' })
        const fd = new FormData()
        fd.append('file', blob, fileName || 'upload.csv')
        const res = await authFetch('/api/import/csv', { method: 'POST', body: fd })
        if (!res.ok) throw new Error(await res.text())
        setParseResult(await res.json())
      } else {
        const res = await authFetch('/api/import/json', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: fileContent }),
        })
        if (!res.ok) throw new Error(await res.text())
        setParseResult(await res.json())
      }
    } catch (err) {
      window.alert(`Parse failed: ${err.message || err}`)
    }
  }, [authFetch, fileContent, fileName, uploadType])

  const toggleRow = useCallback((id) => {
    setSelectedRows((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const selectAllRows = useCallback(() => {
    setSelectedRows(new Set(allRowIds))
  }, [allRowIds])
  const deselectAllRows = useCallback(() => {
    setSelectedRows(new Set())
  }, [])

  const runUploadImport = useCallback(async () => {
    if (!selectedRowObjects.length) return
    setIsImporting(true)
    setImportResult(null)
    const path = uploadType === 'csv' ? '/api/import/csv/confirm' : '/api/import/json/confirm'
    const total = selectedRowObjects.length
    try {
      for (let i = 0; i < total; i++) {
        setImportProgress(`Importing... ${i + 1}/${total}`)
        await new Promise((r) => setTimeout(r, 0))
      }
      const res = await authFetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows: selectedRowObjects }),
      })
      if (!res.ok) throw new Error(await res.text())
      const summary = await res.json()
      setImportResult(summary)
      setImportProgress('')
    } catch (err) {
      setImportProgress('')
      window.alert(`Import failed: ${err.message || err}`)
    } finally {
      setIsImporting(false)
    }
  }, [authFetch, selectedRowObjects, uploadType])

  const runDiscoverAll = useCallback(async () => {
    setIsDiscovering(true)
    setDiscoverResult(null)
    setDiscoverKind(null)
    setSelectedDiscoverIds(new Set())
    setImportResult(null)
    try {
      const res = await authFetch('/api/discover/all')
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setDiscoverResult(data)
      setDiscoverKind('connected')
      const ids = (data.rows || []).map((r) => r.id).filter(Boolean)
      setSelectedDiscoverIds(new Set(ids))
    } catch (err) {
      window.alert(`Discover failed: ${err.message || err}`)
    } finally {
      setIsDiscovering(false)
    }
  }, [authFetch])

  const buildCloudCredentials = useCallback(() => {
    if (discoverProvider === 'aws') {
      return {
        account_id: awsAccountId.trim(),
        regions: Array.from(awsRegions),
      }
    }
    if (discoverProvider === 'gcp') return { project_id: gcpProjectId.trim() }
    if (discoverProvider === 'azure') {
      return {
        subscription_id: azureSubId.trim(),
        tenant_id: azureTenantId.trim(),
      }
    }
    if (discoverProvider === 'github') return { org_name: githubOrg.trim() }
    return {}
  }, [
    discoverProvider,
    awsAccountId,
    awsRegions,
    gcpProjectId,
    azureSubId,
    azureTenantId,
    githubOrg,
  ])

  const runCloudDiscover = useCallback(async () => {
    setIsDiscovering(true)
    setDiscoverResult(null)
    setDiscoverKind(null)
    setSelectedDiscoverIds(new Set())
    setImportResult(null)
    try {
      const res = await authFetch('/api/import/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: discoverProvider,
          credentials: buildCloudCredentials(),
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setDiscoverResult(data)
      setDiscoverKind('cloud')
      const rows = data.rows || data.accounts || []
      const ids = rows.map((r) => r.id).filter(Boolean)
      setSelectedDiscoverIds(new Set(ids))
    } catch (err) {
      window.alert(`Discover failed: ${err.message || err}`)
    } finally {
      setIsDiscovering(false)
    }
  }, [authFetch, discoverProvider, buildCloudCredentials])

  const toggleDiscoverRow = useCallback((id) => {
    setSelectedDiscoverIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const selectAllDiscover = useCallback(() => {
    const ids = discoverRows.map((r) => r.id).filter(Boolean)
    setSelectedDiscoverIds(new Set(ids))
  }, [discoverRows])
  const deselectAllDiscover = useCallback(() => {
    setSelectedDiscoverIds(new Set())
  }, [])

  const selectedDiscoverAccounts = useMemo(() => {
    return discoverRows.filter((r) => r.id && selectedDiscoverIds.has(r.id))
  }, [discoverRows, selectedDiscoverIds])

  const runDiscoverImport = useCallback(async () => {
    if (!selectedDiscoverAccounts.length) return
    setIsImporting(true)
    setImportResult(null)
    const path =
      discoverKind === 'connected' ? '/api/discover/confirm' : '/api/import/discover/confirm'
    try {
      setImportProgress(`Importing... ${selectedDiscoverAccounts.length} accounts`)
      const res = await authFetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accounts: selectedDiscoverAccounts }),
      })
      if (!res.ok) throw new Error(await res.text())
      setImportResult(await res.json())
      setImportProgress('')
    } catch (err) {
      setImportProgress('')
      window.alert(`Import failed: ${err.message || err}`)
    } finally {
      setIsImporting(false)
    }
  }, [authFetch, discoverKind, selectedDiscoverAccounts])

  const toggleAwsRegion = useCallback((id) => {
    setAwsRegions((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const validCount = parseResult?.rows?.length ?? 0
  const errCount = parseResult?.errors?.length ?? 0

  const tabBtn = (id, emoji, label) => (
    <button
      key={id}
      type="button"
      onClick={() => setActiveTab(id)}
      className={`px-4 py-3 text-sm font-semibold border-b-2 transition-colors ${
        activeTab === id
          ? 'border-blue-500 text-blue-400'
          : 'border-transparent text-slate-400 hover:text-slate-200'
      }`}
    >
      <span className="mr-2" aria-hidden>
        {emoji}
      </span>
      {label}
    </button>
  )

  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto w-full min-h-0 pb-12">
      <div>
        <h1 className="text-xl font-bold text-white tracking-tight">Account import</h1>
        <p className="text-sm text-slate-400 mt-1">
          Upload CSV/JSON, auto-discover from connected tools or cloud providers, and review import history.
        </p>
      </div>

      <div className="flex border-b border-border">
        {tabBtn('upload', '📤', 'Upload File')}
        {tabBtn('discover', '🔍', 'Auto-Discover')}
        {tabBtn('history', '📋', 'History')}
      </div>

      {activeTab === 'upload' && (
        <div className="space-y-8">
          <div className="flex rounded-lg border border-border bg-card/40 p-1 w-fit">
            <button
              type="button"
              onClick={() => {
                setUploadType('csv')
                setFileContent('')
                setFileName('')
                setParseResult(null)
              }}
              className={`px-4 py-2 rounded-md text-sm font-medium ${
                uploadType === 'csv' ? 'bg-accent/20 text-accent' : 'text-slate-400'
              }`}
            >
              CSV
            </button>
            <button
              type="button"
              onClick={() => {
                setUploadType('json')
                setFileContent('')
                setFileName('')
                setParseResult(null)
              }}
              className={`px-4 py-2 rounded-md text-sm font-medium ${
                uploadType === 'json' ? 'bg-accent/20 text-accent' : 'text-slate-400'
              }`}
            >
              JSON
            </button>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept={uploadType === 'csv' ? '.csv,text/csv' : '.json,application/json'}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) ingestFile(f)
              e.target.value = ''
            }}
          />

          <div
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click()
            }}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`flex flex-col items-center justify-center w-full h-[200px] rounded-xl border-2 border-dashed cursor-pointer transition-colors ${
              isDragging ? 'border-blue-500 bg-blue-500/10' : 'border-slate-600 bg-slate-900/40 hover:border-slate-500'
            }`}
          >
            <Upload className="w-12 h-12 text-slate-500 mb-3" strokeWidth={1.25} />
            <p className="text-slate-200 font-medium">Drag & drop your {uploadType.toUpperCase()} file here</p>
            <p className="text-sm text-slate-500 mt-1">or click to browse</p>
          </div>

          {uploadType === 'csv' && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <FileText className="w-4 h-4 shrink-0" />
              <span>Need a template?</span>
              <button
                type="button"
                onClick={() => void downloadTemplate()}
                className="inline-flex items-center gap-1.5 text-blue-400 hover:text-blue-300 font-semibold"
              >
                <Download className="w-4 h-4" />
                Download CSV Template
              </button>
            </div>
          )}

          {uploadType === 'json' && (
            <div className="rounded-lg border border-border bg-slate-900/50 overflow-hidden">
              <button
                type="button"
                onClick={() => setShowJsonExample((v) => !v)}
                className="flex items-center justify-between w-full px-4 py-3 text-left text-sm font-medium text-slate-200 hover:bg-slate-800/60"
              >
                <span className="flex items-center gap-2">
                  <Eye className="w-4 h-4" />
                  JSON example format
                </span>
                <ChevronRight className={`w-4 h-4 transition-transform ${showJsonExample ? 'rotate-90' : ''}`} />
              </button>
              {showJsonExample && (
                <pre className="px-4 pb-4 text-xs text-slate-300 overflow-x-auto border-t border-border/60 pt-3 font-mono">
                  {JSON_EXAMPLE}
                </pre>
              )}
            </div>
          )}

          {fileName && (
            <div className="space-y-3">
              <p className="text-sm text-slate-300 flex items-center gap-2">
                <FileText className="w-4 h-4 text-accent" />
                <span className="font-medium text-white">{fileName}</span>
                <span className="text-slate-500">loaded</span>
              </p>
              <PermissionGate resource="import" action="create">
                <button
                  type="button"
                  onClick={() => void runParse()}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 border border-border text-sm font-semibold text-white hover:bg-slate-700"
                >
                  <Search className="w-4 h-4" />
                  Parse & Preview
                </button>
              </PermissionGate>
            </div>
          )}

          {parseResult && (
            <div className="space-y-4 rounded-xl border border-border bg-card/30 p-5">
              <div className="flex flex-wrap items-center gap-4 text-sm">
                <span className="inline-flex items-center gap-1.5 text-emerald-400">
                  <CheckCircle className="w-4 h-4" />
                  {validCount} valid rows
                </span>
                {errCount > 0 && (
                  <span className="inline-flex items-center gap-1.5 text-amber-400">
                    <AlertTriangle className="w-4 h-4" />
                    {errCount} errors
                  </span>
                )}
              </div>

              {errCount > 0 && (
                <div className="rounded-lg border border-red-500/40 bg-red-950/30 overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setParseErrorsOpen((o) => !o)}
                    className="w-full px-3 py-2 text-left text-sm font-semibold text-red-200 flex items-center justify-between"
                  >
                    <span className="flex items-center gap-2">
                      <XCircle className="w-4 h-4" />
                      Parse errors
                    </span>
                    <ChevronRight className={`w-4 h-4 shrink-0 transition-transform ${parseErrorsOpen ? 'rotate-90' : ''}`} />
                  </button>
                  {parseErrorsOpen && (
                    <ul className="px-3 pb-3 space-y-1 text-xs text-red-100/90 font-mono border-t border-red-500/20 pt-2 max-h-40 overflow-y-auto">
                      {(parseResult.errors || []).map((err, i) => (
                        <li key={i}>{err}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <div className="flex items-center justify-between gap-2 flex-wrap">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Preview (first 10 rows)</p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={selectAllRows}
                    className="text-xs font-semibold text-blue-400 hover:text-blue-300"
                  >
                    Select All
                  </button>
                  <button
                    type="button"
                    onClick={deselectAllRows}
                    className="text-xs font-semibold text-slate-400 hover:text-slate-200"
                  >
                    Deselect All
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm text-left">
                  <thead className="bg-slate-900/80 text-slate-400 text-xs uppercase">
                    <tr>
                      <th className="px-3 py-2 w-10">✓</th>
                      <th className="px-3 py-2">Tool</th>
                      <th className="px-3 py-2">Account Name</th>
                      <th className="px-3 py-2">Environment</th>
                      <th className="px-3 py-2">Region</th>
                      <th className="px-3 py-2">Auth Type</th>
                      <th className="px-3 py-2">HITL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.map((row) => {
                      const meta = toolMeta(row.tool_id)
                      const checked = row.id && selectedRows.has(row.id)
                      return (
                        <tr key={row.id || row.account_name} className="border-t border-border/60 hover:bg-slate-800/40">
                          <td className="px-3 py-2">
                            <input
                              type="checkbox"
                              checked={!!checked}
                              onChange={() => row.id && toggleRow(row.id)}
                              className="rounded border-slate-500"
                            />
                          </td>
                          <td className="px-3 py-2 whitespace-nowrap">
                            <span className="mr-1.5">{meta.emoji}</span>
                            <span className="text-slate-200">{meta.label}</span>
                          </td>
                          <td className="px-3 py-2 text-white">{row.account_name}</td>
                          <td className="px-3 py-2">
                            <span
                              className={`inline-flex px-2 py-0.5 rounded-md text-xs font-medium border ${envBadgeClass(row.environment)}`}
                            >
                              {row.environment}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-slate-400">{row.region || '—'}</td>
                          <td className="px-3 py-2 text-slate-400">{row.auth_type}</td>
                          <td className="px-3 py-2">
                            {row.requires_hitl ? (
                              <CheckCircle className="w-4 h-4 text-emerald-400" />
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <PermissionGate resource="import" action="create">
                <button
                  type="button"
                  disabled={!selectedRowObjects.length || isImporting}
                  onClick={() => void runUploadImport()}
                  className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:pointer-events-none text-white font-semibold text-sm"
                >
                  <Upload className="w-4 h-4" />
                  {isImporting ? importProgress || 'Importing...' : `Import ${selectedRowObjects.length} Selected Accounts`}
                </button>
              </PermissionGate>

              {importResult && (
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/25 p-4 text-sm space-y-1">
                  <p className="font-semibold text-emerald-200 flex items-center gap-2">
                    <CheckCircle className="w-4 h-4" />
                    Import finished
                  </p>
                  <p className="text-emerald-300/90">
                    <span className="inline-flex items-center gap-1">
                      <CheckCircle className="w-3.5 h-3.5" /> {importResult.imported ?? 0} imported
                    </span>
                  </p>
                  <p className="text-amber-200/90">
                    <span className="inline-flex items-center gap-1">⏭️ {importResult.skipped ?? 0} skipped (duplicates)</span>
                  </p>
                  <p className="text-red-300/90">
                    <span className="inline-flex items-center gap-1">
                      <XCircle className="w-3.5 h-3.5" /> {importResult.failed ?? 0} failed
                    </span>
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === 'discover' && (
        <div className="space-y-10">
          <div className="rounded-xl border border-border bg-gradient-to-br from-slate-900/80 to-slate-900/40 p-6">
            <div className="flex items-start gap-4">
              <div className="p-3 rounded-lg bg-blue-500/15 border border-blue-500/30">
                <Search className="w-8 h-8 text-blue-400" />
              </div>
              <div className="flex-1 min-w-0">
                <h2 className="text-lg font-bold text-white">Scan all connected tools</h2>
                <p className="text-sm text-slate-400 mt-1">
                  Automatically discover additional accounts from your already-connected integrations (GitHub, Jira, Slack,
                  Kubernetes, Datadog, …).
                </p>
                <PermissionGate resource="import" action="create">
                  <button
                    type="button"
                    disabled={isDiscovering}
                    onClick={() => void runDiscoverAll()}
                    className="mt-4 w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold text-sm"
                  >
                    {isDiscovering ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                    Discover Now
                  </button>
                </PermissionGate>
              </div>
            </div>
          </div>

          <div>
            <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider mb-4">
              Or discover from specific provider
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { id: 'aws', icon: Cloud, label: 'AWS' },
                { id: 'gcp', icon: Cloud, label: 'GCP' },
                { id: 'azure', icon: Database, label: 'Azure' },
                { id: 'github', icon: Github, label: 'GitHub' },
              ].map((p) => {
                const Icon = p.icon
                const active = discoverProvider === p.id
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setDiscoverProvider(p.id)}
                    className={`flex flex-col items-center gap-2 p-4 rounded-xl border transition-colors ${
                      active ? 'border-blue-500 bg-blue-500/10' : 'border-border bg-card/40 hover:border-slate-500'
                    }`}
                  >
                    <Icon className={`w-7 h-7 ${active ? 'text-blue-400' : 'text-slate-400'}`} />
                    <span className={`text-sm font-semibold ${active ? 'text-white' : 'text-slate-400'}`}>{p.label}</span>
                  </button>
                )
              })}
            </div>

            <div className="mt-6 rounded-xl border border-border bg-card/30 p-5 space-y-4">
              {discoverProvider === 'aws' && (
                <>
                  <label className="block text-xs font-semibold text-slate-400 uppercase">Account ID</label>
                  <input
                    value={awsAccountId}
                    onChange={(e) => setAwsAccountId(e.target.value)}
                    placeholder="123456789012"
                    className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
                  />
                  <p className="text-xs text-slate-500 font-semibold uppercase">Regions</p>
                  <div className="flex flex-wrap gap-3">
                    {AWS_REGION_OPTIONS.map((r) => (
                      <label key={r.id} className="inline-flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={awsRegions.has(r.id)}
                          onChange={() => toggleAwsRegion(r.id)}
                          className="rounded border-slate-500"
                        />
                        {r.label}
                      </label>
                    ))}
                  </div>
                  <PermissionGate resource="import" action="create">
                    <button
                      type="button"
                      disabled={isDiscovering}
                      onClick={() => void runCloudDiscover()}
                      className="w-full py-2.5 rounded-lg bg-slate-800 border border-border text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
                    >
                      Discover AWS Accounts
                    </button>
                  </PermissionGate>
                </>
              )}

              {discoverProvider === 'gcp' && (
                <>
                  <label className="block text-xs font-semibold text-slate-400 uppercase">Project ID</label>
                  <input
                    value={gcpProjectId}
                    onChange={(e) => setGcpProjectId(e.target.value)}
                    placeholder="my-gcp-project"
                    className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
                  />
                  <PermissionGate resource="import" action="create">
                    <button
                      type="button"
                      disabled={isDiscovering}
                      onClick={() => void runCloudDiscover()}
                      className="w-full py-2.5 rounded-lg bg-slate-800 border border-border text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
                    >
                      Discover GCP Accounts
                    </button>
                  </PermissionGate>
                </>
              )}

              {discoverProvider === 'azure' && (
                <>
                  <label className="block text-xs font-semibold text-slate-400 uppercase">Subscription ID</label>
                  <input
                    value={azureSubId}
                    onChange={(e) => setAzureSubId(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
                  />
                  <label className="block text-xs font-semibold text-slate-400 uppercase">Tenant ID</label>
                  <input
                    value={azureTenantId}
                    onChange={(e) => setAzureTenantId(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
                  />
                  <PermissionGate resource="import" action="create">
                    <button
                      type="button"
                      disabled={isDiscovering}
                      onClick={() => void runCloudDiscover()}
                      className="w-full py-2.5 rounded-lg bg-slate-800 border border-border text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
                    >
                      Discover Azure Accounts
                    </button>
                  </PermissionGate>
                </>
              )}

              {discoverProvider === 'github' && (
                <>
                  <label className="block text-xs font-semibold text-slate-400 uppercase">Organization name</label>
                  <input
                    value={githubOrg}
                    onChange={(e) => setGithubOrg(e.target.value)}
                    placeholder="acme-corp"
                    className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
                  />
                  <PermissionGate resource="import" action="create">
                    <button
                      type="button"
                      disabled={isDiscovering}
                      onClick={() => void runCloudDiscover()}
                      className="w-full py-2.5 rounded-lg bg-slate-800 border border-border text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
                    >
                      Discover GitHub Accounts
                    </button>
                  </PermissionGate>
                </>
              )}
            </div>
          </div>

          {discoverResult && (
            <div className="space-y-4 rounded-xl border border-border bg-card/30 p-5">
              <p className="text-sm text-slate-300">
                Found{' '}
                <span className="font-bold text-white">{discoverResult.total_discovered ?? discoverResult.total_rows ?? discoverRows.length}</span>{' '}
                accounts across{' '}
                <span className="font-bold text-white">
                  {discoverKind === 'connected'
                    ? discoverResult.sources_scanned ?? 0
                    : 1}{' '}
                </span>
                {discoverKind === 'connected' ? 'connected sources' : 'provider scan'}
              </p>

              <div className="flex gap-2">
                <button type="button" onClick={selectAllDiscover} className="text-xs font-semibold text-blue-400">
                  Select All
                </button>
                <button type="button" onClick={deselectAllDiscover} className="text-xs font-semibold text-slate-400">
                  Deselect All
                </button>
              </div>

              <ul className="space-y-3">
                {discoverRows.map((acc) => {
                  const meta = toolMeta(acc.tool_id)
                  const checked = acc.id && selectedDiscoverIds.has(acc.id)
                  const metaBits = acc.metadata || {}
                  const extra =
                    metaBits.repos != null
                      ? `${metaBits.repos} repos`
                      : metaBits.namespace
                        ? `ns ${metaBits.namespace}`
                        : acc.discovered_services?.length
                          ? `${acc.discovered_services.length} services`
                          : acc.discovered_repos != null
                            ? `${acc.discovered_repos} repos`
                            : null
                  return (
                    <li
                      key={acc.id || acc.account_name}
                      className="flex flex-wrap items-center gap-3 p-4 rounded-lg border border-border/80 bg-slate-900/40"
                    >
                      <input
                        type="checkbox"
                        checked={!!checked}
                        onChange={() => acc.id && toggleDiscoverRow(acc.id)}
                        className="rounded border-slate-500 shrink-0"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-lg">{meta.emoji}</span>
                          <span className="font-semibold text-white truncate">{acc.account_name}</span>
                          <span
                            className={`text-xs px-2 py-0.5 rounded-md border font-medium ${envBadgeClass(acc.environment)}`}
                          >
                            {acc.environment}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 mt-1">
                          {[acc.region, acc.auth_type].filter(Boolean).join(' · ')}
                          {extra ? ` · ${extra}` : ''}
                        </p>
                      </div>
                    </li>
                  )
                })}
              </ul>

              <PermissionGate resource="import" action="create">
                <button
                  type="button"
                  disabled={!selectedDiscoverAccounts.length || isImporting}
                  onClick={() => void runDiscoverImport()}
                  className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:pointer-events-none text-white font-semibold text-sm"
                >
                  <Plus className="w-4 h-4" />
                  {isImporting ? importProgress || 'Importing...' : `Import ${selectedDiscoverAccounts.length} Selected`}
                </button>
              </PermissionGate>

              {importResult && activeTab === 'discover' && (
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/25 p-4 text-sm space-y-1">
                  <p className="font-semibold text-emerald-200">Import finished</p>
                  <p className="text-emerald-300/90">✅ {importResult.imported ?? 0} imported</p>
                  <p className="text-amber-200/90">⏭️ {importResult.skipped ?? 0} skipped</p>
                  <p className="text-red-300/90">❌ {importResult.failed ?? 0} failed</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === 'history' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-400">Last imports (newest first)</p>
            <button
              type="button"
              onClick={() => void loadHistory()}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-400 hover:text-blue-300"
              title="Refresh list"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${historyLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {historyItems.length === 0 && !historyLoading ? (
            <div className="flex flex-col items-center justify-center py-16 rounded-xl border border-dashed border-border text-center">
              <Clock className="w-10 h-10 text-slate-600 mb-3" />
              <p className="text-slate-400 font-medium">No import history yet</p>
              <PermissionGate resource="import" action="create">
                <button
                  type="button"
                  onClick={() => setActiveTab('upload')}
                  className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold"
                >
                  <Upload className="w-4 h-4" />
                  Import your first accounts
                </button>
              </PermissionGate>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto rounded-xl border border-border">
                <table className="w-full text-sm text-left min-w-[720px]">
                  <thead className="bg-slate-900/90 text-slate-400 text-xs uppercase">
                    <tr>
                      <th className="px-3 py-2.5">Date/Time</th>
                      <th className="px-3 py-2.5">Type</th>
                      <th className="px-3 py-2.5">Source</th>
                      <th className="px-3 py-2.5 text-right">Imported</th>
                      <th className="px-3 py-2.5 text-right">Skipped</th>
                      <th className="px-3 py-2.5 text-right">Failed</th>
                      <th className="px-3 py-2.5">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {historyPageSlice.map((h) => {
                      const st = historyStatusRow(h)
                      return (
                        <tr key={h.id} className="border-t border-border/60 hover:bg-slate-800/30">
                          <td className="px-3 py-2.5 text-slate-300 whitespace-nowrap">
                            {formatRelativeTime(h.created_at)}
                          </td>
                          <td className="px-3 py-2.5 text-white">{historyTypeLabel(h.import_type)}</td>
                          <td className="px-3 py-2.5 text-slate-400 max-w-[200px] truncate" title={h.source || ''}>
                            {h.source || '—'}
                          </td>
                          <td className="px-3 py-2.5 text-right text-emerald-400 font-medium">{h.imported ?? 0}</td>
                          <td className="px-3 py-2.5 text-right text-amber-400 font-medium">{h.skipped ?? 0}</td>
                          <td className="px-3 py-2.5 text-right text-red-400 font-medium">{h.failed ?? 0}</td>
                          <td className="px-3 py-2.5">
                            {st.tone === 'ok' && (
                              <span className="inline-flex items-center gap-1 text-emerald-400 text-xs font-semibold">
                                <CheckCircle className="w-3.5 h-3.5" /> {st.label}
                              </span>
                            )}
                            {st.tone === 'partial' && (
                              <span className="inline-flex items-center gap-1 text-amber-400 text-xs font-semibold">
                                <AlertTriangle className="w-3.5 h-3.5" /> {st.label}
                              </span>
                            )}
                            {st.tone === 'fail' && (
                              <span className="inline-flex items-center gap-1 text-red-400 text-xs font-semibold">
                                <XCircle className="w-3.5 h-3.5" /> {st.label}
                              </span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {historyItems.length > 20 && (
                <div className="flex items-center justify-between text-sm text-slate-400">
                  <span>
                    Page {historyPage} of {historyTotalPages}
                  </span>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={historyPage <= 1}
                      onClick={() => setHistoryPage((p) => Math.max(1, p - 1))}
                      className="px-3 py-1 rounded-lg border border-border disabled:opacity-40 text-slate-200"
                    >
                      Previous
                    </button>
                    <button
                      type="button"
                      disabled={historyPage >= historyTotalPages}
                      onClick={() => setHistoryPage((p) => Math.min(historyTotalPages, p + 1))}
                      className="px-3 py-1 rounded-lg border border-border disabled:opacity-40 text-slate-200"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
