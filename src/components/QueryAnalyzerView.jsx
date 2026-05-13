import { useState } from 'react'
import {
  Search, Play, Loader2, CheckCircle2, XCircle, AlertTriangle,
  Lightbulb, Terminal, Sparkles, RefreshCw, Copy, Check,
} from 'lucide-react'
import { API_BASE } from '../config/apiBase'

const DB_OPTIONS = [
  'prod-postgres-primary',
  'prod-postgres-replica',
  'analytics-mysql',
  'reporting-clickhouse',
  'dev-postgres',
]

const EXAMPLE_QUERIES = [
  { label: 'Slow user lookup', sql: "SELECT u.*, p.*, o.* FROM users u\nJOIN profiles p ON p.user_id = u.id\nJOIN orders o ON o.user_id = u.id\nWHERE u.email LIKE '%@example.com'\nORDER BY o.created_at DESC;" },
  { label: 'Unindexed join',   sql: "SELECT e.name, d.department_name, count(s.id) as sale_count\nFROM employees e\nJOIN departments d ON d.id = e.department_id\nJOIN sales s ON s.employee_id = e.id\nWHERE s.created_at > NOW() - INTERVAL '30 days'\nGROUP BY e.name, d.department_name;" },
  { label: 'Full table scan',  sql: "SELECT * FROM audit_log\nWHERE action = 'LOGIN_FAILED'\nAND created_at BETWEEN '2026-01-01' AND '2026-05-01';" },
]

const COST_CFG = {
  Low:        'text-green-400 bg-green-500/10 border-green-500/25',
  Medium:     'text-amber-400 bg-amber-500/10 border-amber-500/25',
  High:       'text-orange-400 bg-orange-500/10 border-orange-500/25',
  'Very High':'text-red-400   bg-red-500/10   border-red-500/25',
  Unknown:    'text-slate-400 bg-slate-500/10 border-slate-500/25',
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  function handle() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <button onClick={handle} className="p-1.5 rounded-lg text-slate-500 hover:text-white hover:bg-slate-800 transition-colors">
      {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
    </button>
  )
}

export default function QueryAnalyzerView() {
  const [query,    setQuery]    = useState('')
  const [database, setDatabase] = useState(DB_OPTIONS[0])
  const [loading,  setLoading]  = useState(false)
  const [result,   setResult]   = useState(null)
  const [error,    setError]    = useState(null)

  async function handleAnalyze() {
    if (!query.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/api/db/analyze-query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), database }),
      })
      if (!res.ok) throw new Error(await res.text())
      setResult(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto pb-16 animate-fade-in">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
          <Search className="w-5 h-5 text-cyan-400" />
          Query Analyzer
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">Paste a SQL query — get EXPLAIN plan, index recommendations, and an AI-powered rewrite</p>
      </div>

      {/* Input panel */}
      <div className="flex flex-col gap-3 p-5 rounded-2xl border border-border bg-card">
        {/* Controls row */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-slate-500 uppercase font-semibold tracking-widest">Database</label>
            <select
              value={database}
              onChange={e => setDatabase(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-cyan-500"
            >
              {DB_OPTIONS.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-slate-500 uppercase font-semibold tracking-widest">Example Queries</label>
            <div className="flex items-center gap-1.5 flex-wrap">
              {EXAMPLE_QUERIES.map(ex => (
                <button
                  key={ex.label}
                  onClick={() => setQuery(ex.sql)}
                  className="px-2.5 py-1.5 rounded-lg border border-slate-700 text-[10px] text-slate-400
                    hover:text-white hover:border-slate-600 transition-colors font-semibold"
                >
                  {ex.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* SQL textarea */}
        <div className="relative">
          <textarea
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Paste your SQL query here…"
            rows={8}
            className="w-full bg-black/60 border border-slate-700 text-green-400 font-mono text-xs rounded-xl px-4 py-3
              focus:outline-none focus:border-cyan-500 resize-none placeholder-slate-700 leading-relaxed"
          />
          {query && (
            <div className="absolute top-2 right-2">
              <CopyButton text={query} />
            </div>
          )}
        </div>

        <button
          onClick={handleAnalyze}
          disabled={loading || !query.trim()}
          className="self-start flex items-center gap-2 px-5 py-2.5 rounded-xl bg-cyan-500/15 border border-cyan-500/35
            text-cyan-400 text-sm font-bold hover:bg-cyan-500/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {loading
            ? <><Loader2 className="w-4 h-4 animate-spin" /> Analyzing…</>
            : <><Sparkles className="w-4 h-4" /> Analyze Query</>
          }
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl border border-red-500/30 bg-red-500/5 text-red-400 text-xs">
          <XCircle className="w-4 h-4 shrink-0" />{error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="flex flex-col gap-4 animate-fade-in">

          {/* Summary bar */}
          <div className="flex items-start gap-3 px-4 py-3.5 rounded-xl border border-slate-700 bg-card">
            {result.is_valid
              ? <CheckCircle2 className="w-4 h-4 text-green-400 shrink-0 mt-0.5" />
              : <XCircle     className="w-4 h-4 text-red-400   shrink-0 mt-0.5" />
            }
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span className="text-xs font-bold text-white">{result.is_valid ? 'Valid Query' : 'Invalid Query'}</span>
                <span className={`text-[10px] px-2 py-0.5 rounded-md border font-semibold ${COST_CFG[result.estimated_cost] ?? COST_CFG.Unknown}`}>
                  Cost: {result.estimated_cost}
                </span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">{result.summary}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

            {/* Issues */}
            {result.issues?.length > 0 && (
              <div className="flex flex-col gap-3 p-4 rounded-2xl border border-amber-500/20 bg-amber-500/5">
                <p className="text-[10px] font-bold text-amber-400 uppercase tracking-widest flex items-center gap-1.5">
                  <AlertTriangle className="w-3 h-3" /> Issues Found
                </p>
                <ul className="flex flex-col gap-2">
                  {result.issues.map((issue, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-slate-300">
                      <span className="w-4 h-4 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-400
                        text-[9px] font-bold flex items-center justify-center shrink-0 mt-0.5">{i + 1}</span>
                      {issue}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Index recommendations */}
            {result.index_recommendations?.length > 0 && (
              <div className="flex flex-col gap-3 p-4 rounded-2xl border border-blue-500/20 bg-blue-500/5">
                <p className="text-[10px] font-bold text-blue-400 uppercase tracking-widest flex items-center gap-1.5">
                  <Lightbulb className="w-3 h-3" /> Index Recommendations
                </p>
                <ul className="flex flex-col gap-2">
                  {result.index_recommendations.map((rec, i) => (
                    <li key={i} className="relative">
                      <pre className="text-[10px] font-mono text-blue-300 bg-black/40 border border-blue-500/20
                        rounded-lg px-3 py-2 overflow-x-auto whitespace-pre-wrap leading-relaxed pr-8">
                        {rec}
                      </pre>
                      <div className="absolute top-1.5 right-1.5"><CopyButton text={rec} /></div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* EXPLAIN plan */}
          {result.explain_plan?.length > 0 && (
            <div className="flex flex-col rounded-2xl border border-slate-700 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2.5 bg-black/60 border-b border-slate-700">
                <div className="flex items-center gap-2">
                  <div className="flex gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
                    <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
                    <span className="w-2.5 h-2.5 rounded-full bg-green-500/60" />
                  </div>
                  <Terminal className="w-3 h-3 text-slate-400" />
                  <span className="text-[10px] font-mono text-slate-400 font-semibold">EXPLAIN ANALYZE — {database}</span>
                </div>
                <CopyButton text={result.explain_plan.join('\n')} />
              </div>
              <pre className="px-4 py-3 bg-black/80 text-[10px] font-mono text-green-400 leading-relaxed overflow-x-auto whitespace-pre">
                {result.explain_plan.join('\n')}
              </pre>
            </div>
          )}

          {/* Rewritten query */}
          {result.rewritten_query && (
            <div className="flex flex-col gap-3 p-4 rounded-2xl border border-green-500/20 bg-green-500/5">
              <p className="text-[10px] font-bold text-green-400 uppercase tracking-widest flex items-center gap-1.5">
                <Sparkles className="w-3 h-3" /> AI-Optimized Rewrite
              </p>
              <div className="relative">
                <pre className="text-[10px] font-mono text-green-300 bg-black/50 border border-green-500/20
                  rounded-xl px-4 py-3 overflow-x-auto whitespace-pre leading-relaxed">
                  {result.rewritten_query}
                </pre>
                <div className="absolute top-2 right-2"><CopyButton text={result.rewritten_query} /></div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
