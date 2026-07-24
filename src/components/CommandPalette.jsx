import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Search,
  Loader2,
  Hexagon,
  AlertTriangle,
  Wrench,
  Server,
  GitBranch,
} from 'lucide-react'
import { API_BASE } from '../config/apiBase'

const ALL_COMMANDS = [
  { label: 'Dashboard', path: '/dashboard', category: 'Navigation' },
  { label: 'Catalog', path: '/catalog', category: 'IDP Platform' },
  { label: 'Dependency Graph', path: '/dependency-graph', category: 'IDP Platform' },
  { label: 'Scorecards', path: '/scorecards', category: 'IDP Platform' },
  { label: 'Standards', path: '/standards', category: 'IDP Platform' },
  { label: 'Entity Actions', path: '/entity-actions', category: 'IDP Platform' },
  { label: 'Golden Paths', path: '/golden-paths', category: 'IDP Platform' },
  { label: 'Template Gallery', path: '/template-gallery', category: 'IDP Platform' },
  { label: 'Reports', path: '/reports', category: 'Reports' },
  { label: 'DORA Metrics', path: '/dora', category: 'Reports' },
  { label: 'Health Dashboard', path: '/health', category: 'Ops' },
  { label: 'Alert Triage', path: '/alerts', category: 'Ops' },
  { label: 'Incidents', path: '/incidents', category: 'Ops' },
  { label: 'Agent Approvals', path: '/approvals', category: 'Ops' },
  { label: 'RBAC Manager', path: '/rbac', category: 'Admin' },
  { label: 'Tool Registry', path: '/tool-registry', category: 'Admin' },
  { label: 'Account Import', path: '/account-import', category: 'Admin' },
  { label: 'Workspaces', path: '/workspaces', category: 'Admin' },
  { label: 'Integrations', path: '/integrations', category: 'Admin' },
  { label: 'Settings', path: '/settings', category: 'Admin' },
  { label: 'AI Assistant', path: '/ai-assistant', category: 'AI' },
  { label: 'CI/CD Pipelines', path: '/cicd', category: 'DevTools' },
  { label: 'GitHub PRs', path: '/github/prs', category: 'DevTools' },
  { label: 'GitHub Actions', path: '/github/actions', category: 'DevTools' },
  { label: 'Live Pipelines', path: '/live-pipelines', category: 'DevTools' },
  { label: 'Deployments', path: '/deployments', category: 'DevTools' },
  { label: 'Schema Browser', path: '/schema-browser', category: 'DevTools' },
  { label: 'Data Lineage', path: '/data-lineage', category: 'DevTools' },
  { label: 'Runbooks', path: '/runbooks', category: 'DevTools' },
]

const TYPE_ORDER = ['Catalog', 'Incident', 'Tool', 'Infra', 'CI/CD']

const TYPE_BADGE = {
  Catalog: 'bg-indigo-500/20 text-indigo-300',
  Incident: 'bg-rose-500/20 text-rose-300',
  Tool: 'bg-emerald-500/20 text-emerald-300',
  Infra: 'bg-amber-500/20 text-amber-300',
  'CI/CD': 'bg-sky-500/20 text-sky-300',
}

const NAV_URL_MAP = {
  '/dashboard': '/dashboard',
  '/catalog': '/catalog',
  '/standards': '/standards',
  '/entity-actions': '/entity-actions',
  '/golden-paths': '/golden-paths',
  '/reports': '/reports',
  '/scorecards': '/scorecards',
  '/dependency-graph': '/dependency-graph',
  '/template-gallery': '/template-gallery',
  '/deployments': '/deployments',
  '/tool-registry': '/tool-registry',
  '/tools': '/tool-registry',
  '/incidents': '/incidents',
  '/alerts': '/alerts',
  '/health': '/health',
  '/approvals': '/approvals',
  '/rbac': '/rbac',
  '/workspaces': '/workspaces',
  '/account-import': '/account-import',
  '/ai-assistant': '/ai-assistant',
  '/cicd': '/cicd',
  '/runbooks': '/runbooks',
  '/integrations': '/integrations',
  '/settings': '/settings',
  '/dora': '/dora',
  '/infra': '/infra',
}

function resolveNavUrl(url) {
  return NAV_URL_MAP[url] || url
}

function groupResults(results) {
  const byType = {}
  for (const row of results) {
    const t = row.type || 'Other'
    if (!byType[t]) byType[t] = []
    if (byType[t].length < 3) byType[t].push(row)
  }
  const groups = []
  const seen = new Set()
  for (const type of TYPE_ORDER) {
    if (byType[type]?.length) {
      groups.push({ type, items: byType[type] })
      seen.add(type)
    }
  }
  for (const [type, items] of Object.entries(byType)) {
    if (!seen.has(type)) groups.push({ type, items })
  }
  return groups
}

function groupNavCommands(commands) {
  const byCategory = {}
  for (const cmd of commands) {
    if (!byCategory[cmd.category]) byCategory[cmd.category] = []
    byCategory[cmd.category].push(cmd)
  }
  return Object.entries(byCategory).map(([category, items]) => ({ category, items }))
}

function TypeIcon({ type }) {
  const cls = 'w-4 h-4 flex-shrink-0 text-slate-400'
  if (type === 'Catalog') return <Hexagon className={cls} />
  if (type === 'Incident') return <AlertTriangle className={cls} />
  if (type === 'Tool') return <Wrench className={cls} />
  if (type === 'Infra') return <Server className={cls} />
  if (type === 'CI/CD') return <GitBranch className={cls} />
  return <Search className={cls} />
}

function TypeBadge({ type }) {
  return (
    <span
      className={`text-xs px-1.5 py-0.5 rounded font-medium shrink-0 ${TYPE_BADGE[type] || 'bg-slate-700 text-slate-300'}`}
    >
      {type}
    </span>
  )
}

export default function CommandPalette({ open: controlledOpen, onClose }) {
  const navigate = useNavigate()
  const inputRef = useRef(null)

  const isControlled = controlledOpen !== undefined && typeof onClose === 'function'
  const [internalOpen, setInternalOpen] = useState(false)
  const open = isControlled ? controlledOpen : internalOpen

  const closePalette = useCallback(() => {
    if (isControlled) onClose()
    else setInternalOpen(false)
  }, [isControlled, onClose])

  const setOpen = useCallback(
    (value) => {
      if (isControlled) {
        const next = typeof value === 'function' ? value(controlledOpen) : value
        if (!next) onClose()
      } else {
        setInternalOpen(value)
      }
    },
    [isControlled, onClose, controlledOpen]
  )
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [loading, setLoading] = useState(false)

  const q = query.trim().toLowerCase()
  const filteredNav = useMemo(() => {
    if (!q) return ALL_COMMANDS
    return ALL_COMMANDS.filter(
      (c) =>
        c.label.toLowerCase().includes(q) ||
        c.path.toLowerCase().includes(q) ||
        c.category.toLowerCase().includes(q)
    )
  }, [q])

  const navGroups = useMemo(() => groupNavCommands(filteredNav), [filteredNav])
  const grouped = useMemo(() => groupResults(results), [results])
  const flatNav = useMemo(() => navGroups.flatMap((g) => g.items), [navGroups])
  const flatSearch = useMemo(() => grouped.flatMap((g) => g.items), [grouped])
  const useSearchMode = q.length >= 2
  const flatResults = useSearchMode ? [...flatNav, ...flatSearch] : flatNav

  const openResult = useCallback(
    (item) => {
      const url = item?.url ?? item?.path
      if (!url) return
      navigate(resolveNavUrl(url))
      closePalette()
      setQuery('')
      setResults([])
      setSelectedIndex(0)
    },
    [navigate, closePalette]
  )

  useEffect(() => {
    if (isControlled) return undefined
    const onOpenEvent = () => setInternalOpen(true)
    window.addEventListener('open-command-palette', onOpenEvent)
    return () => window.removeEventListener('open-command-palette', onOpenEvent)
  }, [isControlled])

  useEffect(() => {
    const onKeyDown = (e) => {
      if (!isControlled && (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setInternalOpen((v) => !v)
        return
      }
      if (!open) return
      if (e.key === 'Escape') {
        e.preventDefault()
        closePalette()
        return
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex((i) => (flatResults.length ? (i + 1) % flatResults.length : 0))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex((i) =>
          flatResults.length ? (i - 1 + flatResults.length) % flatResults.length : 0
        )
        return
      }
      if (e.key === 'Enter' && flatResults[selectedIndex]) {
        e.preventDefault()
        openResult(flatResults[selectedIndex])
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isControlled, open, flatResults, selectedIndex, openResult, closePalette])

  useEffect(() => {
    if (open) {
      const t = window.setTimeout(() => inputRef.current?.focus(), 0)
      return () => window.clearTimeout(t)
    }
    return undefined
  }, [open])

  useEffect(() => {
    setSelectedIndex(0)
    if (!useSearchMode) {
      setResults([])
      setLoading(false)
      return undefined
    }

    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setLoading(true)
      try {
        const token = localStorage.getItem('aiops_access_token')
        const headers = {}
        if (token) headers.Authorization = `Bearer ${token}`
        const res = await fetch(
          `${API_BASE}/api/search?q=${encodeURIComponent(q)}&limit=20`,
          { headers, signal: controller.signal }
        )
        if (!res.ok) throw new Error(await res.text())
        const data = await res.json()
        setResults(Array.isArray(data) ? data : [])
        setSelectedIndex(0)
      } catch (err) {
        if (err.name !== 'AbortError') setResults([])
      } finally {
        setLoading(false)
      }
    }, 300)

    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [query, useSearchMode, q])

  if (!open) return null

  let flatIdx = 0

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] px-4 bg-black/60 backdrop-blur-sm"
      onClick={closePalette}
      role="presentation"
    >
      <div
        className="max-w-xl w-full bg-gray-900 border border-gray-700 rounded-xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-700">
          <Search className="w-5 h-5 text-gray-500 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search pages or anything..."
            className="flex-1 bg-transparent text-white placeholder:text-gray-500 outline-none text-sm"
            autoFocus
          />
          {loading && <Loader2 className="w-4 h-4 text-gray-400 animate-spin shrink-0" />}
        </div>

        <div className="max-h-[min(50vh,360px)] overflow-y-auto py-2">
          {!useSearchMode && filteredNav.length === 0 && (
            <p className="px-4 py-6 text-sm text-gray-500 text-center">No matching pages</p>
          )}

          {!useSearchMode &&
            navGroups.map(({ category, items }) => (
              <div key={category} className="mb-1">
                <p className="px-4 py-1.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  {category}
                </p>
                {items.map((item) => {
                  const idx = flatIdx
                  flatIdx += 1
                  const selected = idx === selectedIndex
                  return (
                    <button
                      key={`nav-${item.path}`}
                      type="button"
                      onClick={() => openResult(item)}
                      onMouseEnter={() => setSelectedIndex(idx)}
                      className={`w-full flex items-center gap-3 px-4 py-2 text-left text-sm transition-colors ${
                        selected ? 'bg-gray-800' : 'hover:bg-gray-800/60'
                      }`}
                    >
                      <span className="flex-1 min-w-0 font-medium text-white truncate">{item.label}</span>
                      <span className="text-gray-500 text-xs shrink-0">{item.path}</span>
                    </button>
                  )
                })}
              </div>
            ))}

          {useSearchMode && !loading && results.length === 0 && filteredNav.length === 0 && (
            <p className="px-4 py-6 text-sm text-gray-500 text-center">
              No results for &ldquo;{query.trim()}&rdquo;
            </p>
          )}

          {useSearchMode &&
            filteredNav.length > 0 &&
            navGroups.map(({ category, items }) => (
              <div key={`nav-${category}`} className="mb-1">
                <p className="px-4 py-1.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  {category}
                </p>
                {items.map((item) => {
                  const idx = flatIdx
                  flatIdx += 1
                  const selected = idx === selectedIndex
                  return (
                    <button
                      key={`nav-${item.path}`}
                      type="button"
                      onClick={() => openResult(item)}
                      onMouseEnter={() => setSelectedIndex(idx)}
                      className={`w-full flex items-center gap-3 px-4 py-2 text-left text-sm transition-colors ${
                        selected ? 'bg-gray-800' : 'hover:bg-gray-800/60'
                      }`}
                    >
                      <span className="flex-1 min-w-0 font-medium text-white truncate">{item.label}</span>
                      <span className="text-gray-500 text-xs shrink-0">{item.path}</span>
                    </button>
                  )
                })}
              </div>
            ))}

          {useSearchMode &&
            grouped.map(({ type, items }) => (
              <div key={type} className="mb-1">
                <p className="px-4 py-1.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">{type}</p>
                {items.map((item) => {
                  const idx = flatIdx
                  flatIdx += 1
                  const selected = idx === selectedIndex
                  return (
                    <button
                      key={`${item.type}-${item.id}-${idx}`}
                      type="button"
                      onClick={() => openResult(item)}
                      onMouseEnter={() => setSelectedIndex(idx)}
                      className={`w-full flex items-center gap-3 px-4 py-2 text-left text-sm transition-colors ${
                        selected ? 'bg-gray-800' : 'hover:bg-gray-800/60'
                      }`}
                    >
                      <TypeBadge type={item.type} />
                      <TypeIcon type={item.type} />
                      <span className="flex-1 min-w-0 font-medium text-white truncate">{item.title}</span>
                      <span className="text-gray-500 truncate max-w-[45%] text-xs">{item.subtitle}</span>
                    </button>
                  )
                })}
              </div>
            ))}
        </div>

        <div className="px-4 py-2 border-t border-gray-700 text-xs text-gray-500 flex flex-wrap gap-x-4 gap-y-1">
          <span>↑↓ navigate</span>
          <span>↵ open</span>
          <span>esc close</span>
        </div>
      </div>
    </div>
  )
}
