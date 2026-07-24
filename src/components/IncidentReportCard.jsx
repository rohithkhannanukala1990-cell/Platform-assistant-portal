import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  AlertCircle,
  Info,
  Target,
  ListChecks,
  ChevronRight,
  Clock,
  Cpu,
  CheckCircle2,
  SearchCode,
  Terminal,
  FolderSearch,
  ShieldCheck,
  FileText,
  Ticket,
  ExternalLink,
  Loader2,
  PlayCircle,
  BookOpen,
  CircleDot,
  CircleCheck,
  ShieldX,
} from 'lucide-react'
import { API_BASE } from '../config/apiBase'

const SEVERITY_CONFIG = {
  Critical: {
    label: 'CRITICAL',
    icon: AlertTriangle,
    badgeCls: 'bg-red-500/15 border-red-500/40 text-red-400',
    glowCls: 'glow-red',
  },
  High: {
    label: 'HIGH',
    icon: AlertCircle,
    badgeCls: 'bg-orange-500/15 border-orange-500/40 text-orange-400',
    glowCls: '',
  },
  Medium: {
    label: 'MEDIUM',
    icon: AlertCircle,
    badgeCls: 'bg-yellow-500/15 border-yellow-500/40 text-yellow-400',
    glowCls: '',
  },
  Warning: {
    label: 'WARNING',
    icon: AlertCircle,
    badgeCls: 'bg-amber-500/15 border-amber-500/40 text-amber-400',
    glowCls: '',
  },
  Low: {
    label: 'LOW',
    icon: Info,
    badgeCls: 'bg-blue-500/15 border-blue-500/40 text-blue-400',
    glowCls: '',
  },
  Unknown: {
    label: 'UNKNOWN',
    icon: Info,
    badgeCls: 'bg-slate-500/15 border-slate-500/40 text-slate-400',
    glowCls: '',
  },
}

export default function IncidentReportCard({
  id,
  severity,
  summary,
  rootCause,
  evidence,
  actionPlan,
  commands,
  filesToCheck,
  validationSteps,
  modelUsed,
  status: initialStatus = 'OPEN',
  executionLogs: initialLogs = null,
}) {
  const config    = SEVERITY_CONFIG[severity] ?? SEVERITY_CONFIG.Unknown
  const BadgeIcon = config.icon

  // Jira state
  const [jiraLoading, setJiraLoading] = useState(false)
  const [jiraResult,  setJiraResult]  = useState(null)

  // Runbook state
  const [runbookLoading, setRunbookLoading] = useState(false)
  const [status,         setStatus]         = useState(initialStatus)
  const [execLogs,       setExecLogs]       = useState(initialLogs)

  async function handleCreateJira() {
    if (!id) return
    setJiraLoading(true); setJiraResult(null)
    try {
      const res  = await fetch(`${API_BASE}/api/incidents/${id}/jira`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail ?? 'Jira API error')
      setJiraResult({ ticket_key: data.ticket_key, ticket_url: data.ticket_url })
    } catch (err) {
      setJiraResult({ error: err.message })
    } finally {
      setJiraLoading(false)
    }
  }

  async function handleRemediate() {
    if (!id) return
    setRunbookLoading(true)
    try {
      const res  = await fetch(`${API_BASE}/api/incidents/${id}/remediate`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail ?? 'Remediation failed')
      setStatus(data.status)
      setExecLogs(data.execution_logs)
    } catch (err) {
      setExecLogs(`ERROR: ${err.message}`)
    } finally {
      setRunbookLoading(false)
    }
  }

  const isOpen            = status === 'OPEN'
  const isResolved        = status === 'RESOLVED'
  const isSecurityRisk    = status === 'ESCALATED_SECURITY_RISK'

  return (
    <div className="flex flex-col gap-4 mt-2">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <h2 className="text-base font-semibold text-white">Incident Report</h2>
          {id && (
            <Link
              to={`/incidents/${id}`}
              className="inline-flex items-center gap-1 text-[11px] font-semibold text-accent hover:underline"
            >
              Command center <ExternalLink className="w-3 h-3" />
            </Link>
          )}

          {/* Severity badge */}
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border ${config.badgeCls} ${config.glowCls}`}>
            <BadgeIcon className="w-3 h-3" strokeWidth={2.5} />
            <span className="text-xs font-bold tracking-widest uppercase">{config.label}</span>
          </span>

          {/* Status badge */}
          {isSecurityRisk ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-red-500/60 bg-red-500/15 text-red-400 animate-pulse">
              <ShieldX className="w-3 h-3" strokeWidth={2.5} />
              <span className="text-xs font-bold tracking-widest">SECURITY RISK</span>
            </span>
          ) : isResolved ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-green-500/40 bg-green-500/10 text-green-400">
              <CircleCheck className="w-3 h-3" strokeWidth={2.5} />
              <span className="text-xs font-bold tracking-widest">RESOLVED</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-red-500/40 bg-red-500/10 text-red-400">
              <CircleDot className="w-3 h-3" strokeWidth={2.5} />
              <span className="text-xs font-bold tracking-widest">OPEN</span>
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-500 flex-wrap">
          <span className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5" />Just now
          </span>
          <span className="flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5" />
            {modelUsed ?? 'LLM'}
          </span>

          {/* Jira button */}
          {id && (
            <button
              onClick={handleCreateJira}
              disabled={jiraLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-blue-500/40 bg-blue-500/10 text-blue-400
                hover:bg-blue-500/20 hover:border-blue-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {jiraLoading
                ? <><Loader2 className="w-3 h-3 animate-spin" />Creating…</>
                : <><Ticket className="w-3 h-3" />Create Jira Ticket</>
              }
            </button>
          )}

          {/* Runbook buttons — only when OPEN (not security risk) and incident is persisted */}
          {id && isOpen && !isSecurityRisk && (
            <>
              <button
                onClick={handleRemediate}
                disabled={runbookLoading}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-accent/40 bg-accent/10 text-accent
                  hover:bg-accent/20 hover:border-accent disabled:opacity-50 disabled:cursor-not-allowed transition-all font-semibold"
              >
                {runbookLoading
                  ? <><Loader2 className="w-3 h-3 animate-spin" />Executing…</>
                  : <><PlayCircle className="w-3 h-3" />Execute Automated Runbook</>
                }
              </button>
              <a
                href="https://wiki.internal.corp/runbooks/"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-600 text-slate-400
                  hover:border-slate-500 hover:text-slate-200 transition-all"
              >
                <BookOpen className="w-3 h-3" />View Internal Runbooks
              </a>
            </>
          )}
        </div>
      </div>

      {/* ── Jira result toast ───────────────────────────────────────────────── */}
      {jiraResult && (
        <div className={`flex items-center justify-between px-4 py-2.5 rounded-xl border text-xs animate-fade-in
          ${jiraResult.error
            ? 'bg-red-500/10 border-red-500/30 text-red-400'
            : 'bg-green-500/10 border-green-500/30 text-green-400'
          }`}
        >
          {jiraResult.error ? (
            <span>Jira error: {jiraResult.error}</span>
          ) : (
            <span className="flex items-center gap-2">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Ticket <strong>{jiraResult.ticket_key}</strong> created!
            </span>
          )}
          {jiraResult.ticket_url && (
            <a
              href={jiraResult.ticket_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 underline hover:text-white transition-colors"
            >
              Open in Jira <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
      )}

      {/* ── AI Safety Guardrail Banner ──────────────────────────────────────── */}
      {isSecurityRisk && (
        <div className="flex items-start gap-3 px-4 py-3.5 rounded-xl border border-red-500/50 bg-red-500/10">
          <ShieldX className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
          <div className="flex flex-col gap-1">
            <p className="text-sm font-bold text-red-400">AI Safety Guardrail Triggered</p>
            <p className="text-xs text-red-300 leading-relaxed">
              The AI agent generated a potentially destructive command that was blocked by the safety
              guardrail. The proposed remediation plan has been cleared.{' '}
              <strong className="text-red-300">Manual intervention is required.</strong>
            </p>
          </div>
        </div>
      )}

      {/* ── Summary ────────────────────────────────────────────────────────── */}
      {summary && (
        <div className="px-4 py-3 rounded-xl bg-slate-800/60 border border-slate-700 text-sm text-slate-300 leading-relaxed">
          <span className="text-slate-500 font-semibold uppercase text-[10px] tracking-widest mr-2">Summary</span>
          {summary}
        </div>
      )}

      {/* ── Root Cause ─────────────────────────────────────────────────────── */}
      {rootCause && (
        <Section icon={Target} title="Root Cause" iconColor="text-orange-400" borderColor="border-orange-500/30">
          <p className="text-sm text-slate-300 leading-relaxed">{rootCause}</p>
        </Section>
      )}

      {/* ── Evidence ───────────────────────────────────────────────────────── */}
      {evidence?.length > 0 && (
        <Section icon={SearchCode} title="Evidence" iconColor="text-purple-400" borderColor="border-purple-500/30">
          <ul className="flex flex-col gap-2">
            {evidence.map((item, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-purple-400 mt-0.5 shrink-0 text-xs">▸</span>
                <code className="text-xs font-mono text-slate-300 leading-relaxed">{item}</code>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* ── Action Plan ────────────────────────────────────────────────────── */}
      {actionPlan?.length > 0 && (
        <Section icon={ListChecks} title="Action Plan" iconColor="text-accent" borderColor="border-accent/30">
          <ol className="flex flex-col gap-3">
            {actionPlan.map((step, i) => (
              <li key={i} className="flex items-start gap-3">
                <span className="flex items-center justify-center w-5 h-5 rounded-full bg-accent/15 border border-accent/30 text-accent text-[10px] font-bold shrink-0 mt-0.5">
                  {i + 1}
                </span>
                <p className="text-sm text-slate-300 leading-relaxed">{step}</p>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {/* ── Commands ───────────────────────────────────────────────────────── */}
      {commands?.length > 0 && (
        <Section icon={Terminal} title="Commands" iconColor="text-cyan-400" borderColor="border-cyan-500/30">
          <div className="flex flex-col gap-2">
            {commands.map((cmd, i) => (
              <code key={i} className="block text-xs font-mono bg-slate-900 text-cyan-300 px-3 py-2 rounded-lg border border-slate-700 leading-relaxed whitespace-pre-wrap break-all">
                {cmd}
              </code>
            ))}
          </div>
        </Section>
      )}

      {/* ── Files to Check ─────────────────────────────────────────────────── */}
      {filesToCheck?.length > 0 && (
        <Section icon={FolderSearch} title="Files to Check" iconColor="text-yellow-400" borderColor="border-yellow-500/30">
          <ul className="flex flex-col gap-2">
            {filesToCheck.map((file, i) => (
              <li key={i} className="flex items-start gap-2">
                <FileText className="w-3.5 h-3.5 text-yellow-400 shrink-0 mt-0.5" />
                <code className="text-xs font-mono text-slate-300 leading-relaxed">{file}</code>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* ── Validation Steps ───────────────────────────────────────────────── */}
      {validationSteps?.length > 0 && (
        <Section icon={ShieldCheck} title="Validation Steps" iconColor="text-green-400" borderColor="border-green-500/30">
          <ul className="flex flex-col gap-2">
            {validationSteps.map((check, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-300 leading-relaxed">
                <CheckCircle2 className="w-3.5 h-3.5 text-green-400 shrink-0 mt-0.5" />
                <span>{check}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between pt-3 border-t border-border">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <div className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" />
          Awaiting human confirmation before applying changes
        </div>
        {/* Only show Mark Resolved button when OPEN and no runbook active */}
        {isOpen && !runbookLoading && (
          <button
            onClick={handleRemediate}
            className="flex items-center gap-1.5 text-xs font-medium text-accent hover:text-white border border-accent/30 hover:border-accent/60 hover:bg-accent/10 px-3 py-1.5 rounded-lg transition-all duration-150"
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            Mark Resolved
            <ChevronRight className="w-3 h-3 opacity-60" />
          </button>
        )}
      </div>

      {/* ── Execution Logs (terminal output) ───────────────────────────────── */}
      {execLogs && (
        <div className="flex flex-col rounded-xl border border-green-500/20 overflow-hidden animate-fade-in">
          <div className="flex items-center gap-2.5 px-4 py-2.5 bg-black/60 border-b border-green-500/20">
            <div className="flex gap-1.5">
              <span className="w-3 h-3 rounded-full bg-red-500/70" />
              <span className="w-3 h-3 rounded-full bg-yellow-500/70" />
              <span className="w-3 h-3 rounded-full bg-green-500/70" />
            </div>
            <span className="text-xs font-mono text-green-400 font-semibold">
              automated-runbook — incident-{id}
            </span>
            <span className="ml-auto flex items-center gap-1.5 text-[10px] text-green-500">
              <CircleCheck className="w-3 h-3" />
              EXECUTION COMPLETE
            </span>
          </div>
          <pre className="p-4 bg-black text-xs font-mono text-green-400 leading-relaxed overflow-x-auto whitespace-pre">
            {execLogs}
          </pre>
        </div>
      )}

    </div>
  )
}

function Section({ icon: Icon, title, iconColor, borderColor, children }) {
  return (
    <div className={`flex flex-col gap-3 p-4 rounded-xl bg-card border ${borderColor}`}>
      <div className="flex items-center gap-2">
        <Icon className={`w-4 h-4 ${iconColor}`} strokeWidth={2} />
        <h3 className="text-sm font-semibold text-white">{title}</h3>
      </div>
      {children}
    </div>
  )
}
