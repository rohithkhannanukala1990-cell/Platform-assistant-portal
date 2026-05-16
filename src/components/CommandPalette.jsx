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

const TYPE_ORDER = ['Catalog', 'Incident', 'Tool', 'Infra', 'CI/CD']

const TYPE_BADGE = {
  Catalog: 'bg-indigo-500/20 text-indigo-300',
  Incident: 'bg-rose-500/20 text-rose-300',
  Tool: 'bg-emerald-500/20 text-emerald-300',
  Infra: 'bg-amber-500/20 text-amber-300',
  'CI/CD': 'bg-sky-500/20 text-sky-300',
}

const NAV_URL_MAP = {
  '/catalog': '/developer',
  '/incidents': '/ops?view=triage',
  '/tools': '/ops?view=tool-registry',
  '/infra': '/ops?view=infra',
  '/cicd': '/ops?view=cicd',
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

export default function CommandPalette() {
  const navigate = useNavigate()
  const inputRef = useRef(null)

  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [loading, setLoading] = useState(false)

  const grouped = useMemo(() => groupResults(results), [results])
  const flatResults = useMemo(() => grouped.flatMap((g) => g.items), [grouped])

  const openResult = useCallback(
    (item) => {
      if (!item?.url) return
      navigate(resolveNavUrl(item.url))
      setOpen(false)
      setQuery('')
      setResults([])
      setSelectedIndex(0)
    },
    [navigate]
  )

  useEffect(() => {
    const onKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen(true)
        return
      }
      if (!open) return
      if (e.key === 'Escape') {
        e.preventDefault()
        setOpen(false)
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
  }, [open, flatResults, selectedIndex, openResult])

  useEffect(() => {
    if (open) {
      const t = window.setTimeout(() => inputRef.current?.focus(), 0)
      return () => window.clearTimeout(t)
    }
    return undefined
  }, [open])

  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      setSelectedIndex(0)
      setLoading(false)
      return undefined
    }

    if (query.trim().length < 2) {
      setResults([])
      setSelectedIndex(0)
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
          `${API_BASE}/api/search?q=${encodeURIComponent(query.trim())}&limit=20`,
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
  }, [query])

  if (!open) return null

  let flatIdx = 0

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] px-4 bg-black/60 backdrop-blur-sm"
      onClick={() => setOpen(false)}
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
            placeholder="Search anything..."
            className="flex-1 bg-transparent text-white placeholder:text-gray-500 outline-none text-sm"
            autoFocus
          />
          {loading && <Loader2 className="w-4 h-4 text-gray-400 animate-spin shrink-0" />}
        </div>

        <div className="max-h-[min(50vh,360px)] overflow-y-auto py-2">
          {query.trim().length >= 2 && !loading && results.length === 0 && (
            <p className="px-4 py-6 text-sm text-gray-500 text-center">
              No results for &ldquo;{query.trim()}&rdquo;
            </p>
          )}

          {query.trim().length < 2 && (
            <p className="px-4 py-6 text-sm text-gray-500 text-center">Type at least 2 characters to search</p>
          )}

          {grouped.map(({ type, items }) => (
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
