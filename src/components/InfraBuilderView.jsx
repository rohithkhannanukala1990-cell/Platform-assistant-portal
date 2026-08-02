import { useState } from 'react'
import {
  Construction,
  Sparkles,
  Copy,
  Check,
  DollarSign,
  Terminal,
  FileCode2,
  ChevronDown,
  AlertOctagon,
  Cpu,
  Cloud,
} from 'lucide-react'
import { API_BASE } from '../config/apiBase'
import RelatedAgentsBar from './RelatedAgentsBar'

const API_URL = `${API_BASE}/api/infra/generate`

const PROVIDERS = [
  {
    id: 'AWS',
    label: 'AWS',
    logo: '🟧',
    description: 'Amazon Web Services',
    color: 'border-orange-500/40 bg-orange-500/10 text-orange-300',
    activeRing: 'ring-2 ring-orange-500/60',
  },
  {
    id: 'GCP',
    label: 'GCP',
    logo: '🔵',
    description: 'Google Cloud',
    color: 'border-blue-500/40 bg-blue-500/10 text-blue-300',
    activeRing: 'ring-2 ring-blue-500/60',
  },
  {
    id: 'Azure',
    label: 'Azure',
    logo: '🔷',
    description: 'Microsoft Azure',
    color: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
    activeRing: 'ring-2 ring-sky-500/60',
  },
  {
    id: 'DigitalOcean',
    label: 'DigitalOcean',
    logo: '🌊',
    description: 'DigitalOcean',
    color: 'border-cyan-500/40 bg-cyan-500/10 text-cyan-300',
    activeRing: 'ring-2 ring-cyan-500/60',
  },
]

const EXAMPLES = {
  AWS:          ['Free-tier web server for a Node.js app', 'S3 bucket for static website hosting', 'RDS PostgreSQL on free tier', 'VPC with public and private subnets'],
  GCP:          ['Free-tier VM to host a Flask API', 'Cloud Storage bucket for static assets', 'Cloud SQL PostgreSQL on free tier', 'Cloud Run service for a containerized app'],
  Azure:        ['Free-tier VM for a web server', 'Blob storage account for backups', 'Azure SQL Database on free tier', 'App Service for a Node.js app'],
  DigitalOcean: ['Cheapest Droplet for a Node.js app', 'Spaces bucket for static file storage', 'PostgreSQL managed database cluster', 'App Platform for a containerized service'],
}

function CopyButton({ text, size = 'sm' }) {
  const [copied, setCopied] = useState(false)
  async function handleCopy() {
    try { await navigator.clipboard.writeText(text) }
    catch {
      const el = document.createElement('textarea')
      el.value = text
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-lg
        border border-slate-700 text-slate-400 hover:text-white hover:border-slate-500
        bg-slate-900/80 transition-all duration-150 shrink-0"
    >
      {copied
        ? <><Check className="w-3 h-3 text-accent" />Copied!</>
        : <><Copy className="w-3 h-3" />Copy</>}
    </button>
  )
}

function CodePane({ title, icon: Icon, iconColor, borderColor, language, plainText, children }) {
  return (
    <div className={`flex flex-col rounded-xl border ${borderColor} bg-card overflow-hidden flex-1 min-w-0`}>
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-sidebar shrink-0">
        <div className="flex items-center gap-2">
          <Icon className={`w-3.5 h-3.5 ${iconColor}`} />
          <span className="text-xs font-semibold text-white">{title}</span>
          {language && (
            <span className="text-[10px] text-slate-600 font-mono border border-slate-700 rounded px-1.5 py-0.5">
              {language}
            </span>
          )}
        </div>
        {plainText && <CopyButton text={plainText} />}
      </div>
      <div className="flex-1 overflow-auto">{children}</div>
    </div>
  )
}

export default function InfraBuilderView({ selectedRecord, onClearRecord, onGenerateComplete }) {
  const [provider, setProvider] = useState('GCP')
  const [prompt, setPrompt]     = useState('')
  const [result, setResult]     = useState(null)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)

  const displayResult   = selectedRecord ?? result
  const displayProvider = selectedRecord?.provider_used ?? provider
  const activeProvider  = PROVIDERS.find((p) => p.id === displayProvider) ?? PROVIDERS.find((p) => p.id === provider)

  function handleClear() {
    setPrompt('')
    setResult(null)
    setError(null)
    onClearRecord?.()
  }

  async function handleGenerate() {
    if (!prompt.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    onClearRecord?.()
    try {
      const res = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, provider }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `Server error ${res.status}`)
      }
      setResult(await res.json())
      onGenerateComplete?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-5xl w-full mx-auto">

      {/* ── Page Header ──────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Construction className="w-5 h-5 text-accent" strokeWidth={2} />
            <h1 className="text-xl font-bold text-white tracking-tight">Infra Builder</h1>
          </div>
          <p className="text-sm text-slate-400">
            Describe what you need — get Terraform code and CLI commands for any cloud provider.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500 border border-border rounded-lg px-3 py-2 bg-card">
          <Cpu className="w-3.5 h-3.5 text-accent" />
          <span>{result?.model_used ?? 'LLM'}</span>
          <div className="w-1.5 h-1.5 rounded-full bg-accent" />
        </div>
      </div>

      <RelatedAgentsBar surface="infra" />

      {/* ── Viewing history banner ───────────────────────────────────────── */}
      {selectedRecord && (
        <div className="flex items-center justify-between px-4 py-2.5 rounded-xl border border-accent/30 bg-accent/5">
          <div className="flex items-center gap-2 text-xs text-slate-300">
            <span className="text-accent font-semibold">Viewing Infra Record #{selectedRecord.id}</span>
            <span className="text-slate-600">—</span>
            <span className="text-slate-500">{new Date(selectedRecord.timestamp).toLocaleString()}</span>
          </div>
          <button onClick={handleClear} className="flex items-center gap-1.5 text-xs text-accent hover:text-white transition-colors">
            ← Back to Builder
          </button>
        </div>
      )}

      {/* ── Provider Selector (hidden when viewing history) ──────────────── */}
      {!selectedRecord && (<div className="flex flex-col gap-3">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest">
          Select Cloud Provider
        </p>
        <div className="grid grid-cols-4 gap-3">
          {PROVIDERS.map((p) => (
            <button
              key={p.id}
              onClick={() => { setProvider(p.id); setResult(null); setError(null) }}
              className={`flex flex-col items-center gap-2 px-3 py-4 rounded-xl border transition-all duration-150
                ${provider === p.id
                  ? `${p.color} ${p.activeRing}`
                  : 'border-border bg-card text-slate-500 hover:border-slate-600 hover:text-slate-300'
                }`}
            >
              <span className="text-2xl">{p.logo}</span>
              <span className="text-xs font-bold tracking-wide">{p.label}</span>
              <span className="text-[10px] text-center opacity-70">{p.description}</span>
            </button>
          ))}
        </div>
      </div>)}

      {/* ── Prompt Input (hidden when viewing history) ───────────────────── */}
      {!selectedRecord && (<div className="flex flex-col rounded-xl border border-border bg-card overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-sidebar text-xs text-slate-500">
          <Cloud className="w-3.5 h-3.5" />
          <span>
            Describe your{' '}
            <span className={`font-semibold ${activeProvider?.color.split(' ').pop()}`}>
              {activeProvider?.description}
            </span>{' '}
            infrastructure need
          </span>
        </div>

        <textarea
          className="w-full h-24 bg-transparent px-4 py-3.5 text-sm text-slate-300 placeholder-slate-600 resize-none outline-none leading-relaxed"
          placeholder={`e.g. ${EXAMPLES[provider][0]}`}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleGenerate() }}
          spellCheck={false}
        />

        {/* Example chips */}
        <div className="flex flex-wrap gap-2 px-4 pb-3">
          {EXAMPLES[provider].map((ex) => (
            <button
              key={ex}
              onClick={() => setPrompt(ex)}
              className="text-[11px] text-slate-500 hover:text-slate-300 border border-slate-700 hover:border-slate-600 rounded-lg px-2.5 py-1 bg-slate-900 transition-colors"
            >
              {ex}
            </button>
          ))}
        </div>
      </div>)}

      {/* ── Generate Button (hidden when viewing history) ────────────────── */}
      {!selectedRecord && (<div className="flex items-center gap-3">
        <button
          onClick={handleGenerate}
          disabled={!prompt.trim() || loading}
          className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold bg-accent text-black
            hover:bg-green-400 active:scale-95
            disabled:opacity-40 disabled:cursor-not-allowed disabled:scale-100
            transition-all duration-150 glow-green"
        >
          {loading ? (
            <><span className="w-4 h-4 border-2 border-black/30 border-t-black rounded-full animate-spin" />Generating…</>
          ) : (
            <><Sparkles className="w-4 h-4" />Generate for {provider}</>
          )}
        </button>
        <p className="text-xs text-slate-600 italic">
          {loading ? `Designing ${provider} infrastructure…` : !prompt.trim() ? 'Describe your infra above' : 'Ctrl+Enter to generate'}
        </p>
      </div>)}

      {/* ── Error Banner ─────────────────────────────────────────────────── */}
      {error && (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/30 animate-fade-in">
          <AlertOctagon className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-red-400">Generation Failed</p>
            <p className="text-xs text-slate-400 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* ── Result ───────────────────────────────────────────────────────── */}
      {displayResult && (
        <div className="flex flex-col gap-4 animate-fade-in">
          {/* Divider */}
          {!selectedRecord && (<div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-border" />
            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              <ChevronDown className="w-3.5 h-3.5 text-accent" />
              Infrastructure Plan Ready
            </div>
            <div className="flex-1 h-px bg-border" />
          </div>)}

          {/* Meta strip */}
          <div className="flex flex-wrap items-stretch gap-3">
            <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl border border-border bg-card flex-1 min-w-48">
              <span className="text-xl">{activeProvider?.logo}</span>
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Resource</p>
                <p className="text-sm font-semibold text-white mt-0.5">{displayResult.resource_name}</p>
              </div>
            </div>

            <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl border border-border bg-card min-w-32">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Provider</p>
                <p className={`text-sm font-bold mt-0.5 ${activeProvider?.color.split(' ').pop()}`}>
                  {displayResult.provider_used}
                </p>
              </div>
            </div>

            <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl border border-accent/30 bg-accent/5 flex-[3] min-w-60">
              <DollarSign className="w-4 h-4 text-accent shrink-0 mt-0.5" />
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Cost Estimate</p>
                <p className="text-xs text-slate-300 leading-relaxed mt-0.5">{displayResult.cost_estimate}</p>
              </div>
            </div>
          </div>

          {/* Split pane */}
          <div className="flex gap-4 min-h-[420px]">
            {/* Terraform */}
            <CodePane
              title="Terraform (HCL)"
              icon={FileCode2}
              iconColor="text-violet-400"
              borderColor="border-violet-500/30"
              language="HCL"
              plainText={displayResult.terraform_code}
            >
              <pre className="p-4 text-xs font-mono text-violet-200 leading-relaxed whitespace-pre overflow-x-auto">
                <code>{displayResult.terraform_code}</code>
              </pre>
            </CodePane>

            {/* CLI commands */}
            <CodePane
              title={`${displayResult.provider_used} CLI Commands`}
              icon={Terminal}
              iconColor="text-cyan-400"
              borderColor="border-cyan-500/30"
              plainText={displayResult.cli_commands.join('\n')}
            >
              <div className="flex flex-col gap-2 p-4">
                {displayResult.cli_commands.map((cmd, i) => (
                  <div key={i} className="flex items-start gap-2 group">
                    <span className="text-slate-700 text-xs font-mono mt-2 shrink-0 w-5 text-right">
                      {i + 1}
                    </span>
                    <code className="flex-1 text-xs font-mono text-cyan-300 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 leading-relaxed whitespace-pre-wrap break-all">
                      {cmd}
                    </code>
                    <div className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-1">
                      <CopyButton text={cmd} />
                    </div>
                  </div>
                ))}
              </div>
            </CodePane>
          </div>
        </div>
      )}
    </div>
  )
}
