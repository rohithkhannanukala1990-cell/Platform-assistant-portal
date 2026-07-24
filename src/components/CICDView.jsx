import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Rocket,
  Sparkles,
  Copy,
  Check,
  Terminal,
  ChevronDown,
  AlertOctagon,
  Cpu,
  FileText,
  ShieldCheck,
  BookOpen,
  GitBranch,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE } from '../config/apiBase'

const API_URL = `${API_BASE}/api/cicd/generate`

const TOOLS = [
  {
    id: 'GitHub Actions',
    label: 'GitHub Actions',
    logo: '🐙',
    file: '.github/workflows/main.yml',
    color: 'border-purple-500/40 bg-purple-500/10 text-purple-300',
    ring: 'ring-2 ring-purple-500/60',
    codeColor: 'text-purple-200',
  },
  {
    id: 'GitLab CI',
    label: 'GitLab CI',
    logo: '🦊',
    file: '.gitlab-ci.yml',
    color: 'border-orange-500/40 bg-orange-500/10 text-orange-300',
    ring: 'ring-2 ring-orange-500/60',
    codeColor: 'text-orange-200',
  },
  {
    id: 'Jenkins',
    label: 'Jenkins',
    logo: '🤖',
    file: 'Jenkinsfile',
    color: 'border-red-500/40 bg-red-500/10 text-red-300',
    ring: 'ring-2 ring-red-500/60',
    codeColor: 'text-red-200',
  },
]

const EXAMPLES = {
  'GitHub Actions': [
    'FastAPI backend and React frontend deploying to AWS EC2',
    'Node.js Express app deploying to AWS Lambda',
    'Docker containerized app pushing to GitHub Container Registry',
    'Python Django app with PostgreSQL deploying to Heroku',
  ],
  'GitLab CI': [
    'FastAPI and React app deploying to GCP Cloud Run',
    'Java Spring Boot app deploying to a self-hosted server',
    'Next.js app building and deploying to Netlify',
    'Go microservice with Docker deploying to Kubernetes',
  ],
  Jenkins: [
    'Java Maven app deploying to AWS Elastic Beanstalk',
    'Node.js app building Docker image and pushing to ECR',
    'Python Flask app running tests and deploying to Azure',
    'Gradle Android build pipeline with test and artifact upload',
  ],
}

function CopyButton({ text }) {
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
    setTimeout(() => setCopied(false), 2200)
  }
  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-lg
        border border-slate-700 text-slate-400 hover:text-white hover:border-slate-500
        bg-slate-900/80 transition-all duration-150"
    >
      {copied
        ? <><Check className="w-3 h-3 text-accent" />Copied!</>
        : <><Copy className="w-3 h-3" />Copy</>}
    </button>
  )
}

function InfoCard({ icon: Icon, iconColor, borderColor, title, children }) {
  return (
    <div className={`flex flex-col gap-3 p-4 rounded-xl border ${borderColor} bg-card`}>
      <div className="flex items-center gap-2">
        <Icon className={`w-4 h-4 ${iconColor}`} strokeWidth={2} />
        <h3 className="text-sm font-semibold text-white">{title}</h3>
      </div>
      {children}
    </div>
  )
}

export default function CICDView({ selectedRecord, onClearRecord, onGenerateComplete }) {
  const navigate = useNavigate()
  const { authFetch } = useAuth()
  const [tool, setTool]       = useState('GitHub Actions')
  const [prompt, setPrompt]   = useState('')
  const [result, setResult]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  const displayResult = selectedRecord ?? result
  const activeTool    = TOOLS.find((t) => t.id === (selectedRecord?.tool_name ?? tool)) ?? TOOLS[0]

  function handleClear() {
    setPrompt(''); setResult(null); setError(null); onClearRecord?.()
  }

  async function handleGenerate() {
    if (!prompt.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await authFetch('/api/cicd/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, cicd_tool: tool }),
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
            <Rocket className="w-5 h-5 text-accent" strokeWidth={2} />
            <h1 className="text-xl font-bold text-white tracking-tight">CI/CD Pipeline</h1>
          </div>
          <p className="text-sm text-slate-400">
            Describe your app and deployment target — get a production-ready pipeline file instantly.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
            <button
              type="button"
              onClick={() => navigate('/live-pipelines')}
              className="text-indigo-400 hover:text-indigo-300 underline transition-colors"
            >
              View Live Pipelines →
            </button>
            <a
              href="/tool-registry"
              className="text-slate-500 hover:text-slate-300 transition-colors"
            >
              Connect GitHub in Tool Registry
            </a>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500 border border-border rounded-lg px-3 py-2 bg-card">
          <Cpu className="w-3.5 h-3.5 text-accent" />
          <span>{result?.model_used ?? 'LLM'}</span>
          <div className="w-1.5 h-1.5 rounded-full bg-accent" />
        </div>
      </div>

      {/* ── History banner ───────────────────────────────────────────────── */}
      {selectedRecord && (
        <div className="flex items-center justify-between px-4 py-2.5 rounded-xl border border-accent/30 bg-accent/5">
          <div className="flex items-center gap-2 text-xs text-slate-300">
            <span className="text-accent font-semibold">Viewing Pipeline #{selectedRecord.id}</span>
            <span className="text-slate-600">—</span>
            <span className="text-slate-500">{new Date(selectedRecord.timestamp).toLocaleString()}</span>
          </div>
          <button onClick={handleClear} className="flex items-center gap-1.5 text-xs text-accent hover:text-white transition-colors">
            ← Back to Builder
          </button>
        </div>
      )}

      {/* ── Tool Selector + Prompt + Button (hidden when viewing history) ── */}
      {!selectedRecord && (
        <>
          <div className="flex flex-col gap-3">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-widest">
              Select CI/CD Tool
            </p>
            <div className="grid grid-cols-3 gap-3">
              {TOOLS.map((t) => (
                <button
                  key={t.id}
                  onClick={() => { setTool(t.id); setResult(null); setError(null) }}
                  className={`flex flex-col items-center gap-2 px-4 py-5 rounded-xl border transition-all duration-150
                    ${tool === t.id
                      ? `${t.color} ${t.ring}`
                      : 'border-border bg-card text-slate-500 hover:border-slate-600 hover:text-slate-300'
                    }`}
                >
                  <span className="text-3xl">{t.logo}</span>
                  <span className="text-sm font-bold tracking-wide">{t.label}</span>
                  <code className="text-[10px] font-mono opacity-60">{t.file}</code>
                </button>
              ))}
            </div>
          </div>

          {/* ── Prompt Input ─────────────────────────────────────────────── */}
          <div className="flex flex-col rounded-xl border border-border bg-card overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-sidebar text-xs text-slate-500">
              <GitBranch className="w-3.5 h-3.5" />
              <span>
                Describe your app and deployment target for{' '}
                <span className={`font-semibold ${activeTool?.color.split(' ').pop()}`}>
                  {activeTool?.label}
                </span>
              </span>
            </div>
            <textarea
              className="w-full h-24 bg-transparent px-4 py-3.5 text-sm text-slate-300 placeholder-slate-600 resize-none outline-none leading-relaxed"
              placeholder={`e.g. ${EXAMPLES[tool][0]}`}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleGenerate() }}
              spellCheck={false}
            />
            <div className="flex flex-wrap gap-2 px-4 pb-3">
              {EXAMPLES[tool].map((ex) => (
                <button
                  key={ex}
                  onClick={() => setPrompt(ex)}
                  className="text-[11px] text-slate-500 hover:text-slate-300 border border-slate-700 hover:border-slate-600 rounded-lg px-2.5 py-1 bg-slate-900 transition-colors"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>

          {/* ── Generate Button ──────────────────────────────────────────── */}
          <div className="flex items-center gap-3">
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
                <><Sparkles className="w-4 h-4" />Generate {tool} Pipeline</>
              )}
            </button>
            <p className="text-xs text-slate-600 italic">
              {loading
                ? `Building your ${tool} pipeline…`
                : !prompt.trim()
                ? 'Describe your app above'
                : 'Ctrl+Enter to generate'}
            </p>
          </div>
        </>
      )}

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
              Pipeline Ready
            </div>
            <div className="flex-1 h-px bg-border" />
          </div>)}

          {/* File badge */}
          <div className="flex items-center gap-3">
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border ${activeTool?.color} text-xs font-mono`}>
              <FileText className="w-3.5 h-3.5" />
              {activeTool?.file}
            </div>
            <span className="text-xs text-slate-500">{displayResult.tool_name} pipeline — ready to commit</span>
          </div>

          {/* YAML code block — full width */}
          <div className="flex flex-col rounded-xl border border-border bg-card overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-sidebar">
              <div className="flex items-center gap-2">
                <Terminal className={`w-3.5 h-3.5 ${activeTool?.color.split(' ').pop()}`} />
                <span className="text-xs font-semibold text-white">Pipeline Code</span>
                <span className="text-[10px] text-slate-600 font-mono border border-slate-700 rounded px-1.5 py-0.5">
                  {activeTool?.id === 'Jenkins' ? 'Groovy' : 'YAML'}
                </span>
              </div>
              <CopyButton text={displayResult.yaml_code} />
            </div>
            <div className="overflow-auto max-h-[520px]">
              <pre className={`p-4 text-xs font-mono leading-relaxed whitespace-pre ${activeTool?.codeColor ?? 'text-slate-300'}`}>
                <code>{displayResult.yaml_code}</code>
              </pre>
            </div>
          </div>

          {/* Explanation + Security side by side */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Explanation */}
            <InfoCard
              icon={BookOpen}
              iconColor="text-blue-400"
              borderColor="border-blue-500/30"
              title="Pipeline Explanation"
            >
              <p className="text-sm text-slate-300 leading-relaxed">{displayResult.explanation}</p>
            </InfoCard>

            {/* Security checks */}
            {Array.isArray(displayResult.security_checks) && displayResult.security_checks.length > 0 && (
              <InfoCard
                icon={ShieldCheck}
                iconColor="text-green-400"
                borderColor="border-green-500/30"
                title="Security &amp; Quality Checks"
              >
                <ul className="flex flex-col gap-2.5">
                  {displayResult.security_checks.map((check, i) => (
                    <li key={i} className="flex items-start gap-2.5">
                      <span className="flex items-center justify-center w-5 h-5 rounded-full bg-green-500/15 border border-green-500/30 text-green-400 text-[10px] font-bold shrink-0 mt-0.5">
                        {i + 1}
                      </span>
                      <span className="text-sm text-slate-300 leading-relaxed">{check}</span>
                    </li>
                  ))}
                </ul>
              </InfoCard>
            )}
          </div>

          {/* Commit tip */}
          <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-800/50 border border-slate-700 text-xs text-slate-500">
            <GitBranch className="w-3.5 h-3.5 text-accent shrink-0" />
            <span>
              Copy the code above → create{' '}
              <code className="font-mono bg-slate-900 text-slate-300 px-1.5 py-0.5 rounded">
                {activeTool?.file}
              </code>{' '}
              in your repo root → commit and push to trigger the pipeline.
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
