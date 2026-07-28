import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  ClipboardCopy,
  Clock,
  Download,
  ExternalLink,
  FileText,
  GitBranch,
  Info,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Terminal,
  XCircle,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from './ToastNotification'

const SEVERITY_CFG = {
  Critical: { cls: 'bg-red-500/15 border-red-500/40 text-red-400', icon: AlertTriangle },
  High: { cls: 'bg-orange-500/15 border-orange-500/40 text-orange-400', icon: AlertCircle },
  Medium: { cls: 'bg-yellow-500/15 border-yellow-500/40 text-yellow-400', icon: AlertCircle },
  Warning: { cls: 'bg-amber-500/15 border-amber-500/40 text-amber-400', icon: AlertCircle },
  Low: { cls: 'bg-blue-500/15 border-blue-500/40 text-blue-400', icon: Info },
  Unknown: { cls: 'bg-slate-500/15 border-slate-500/40 text-slate-400', icon: Info },
}

const STATUS_CLS = {
  OPEN: 'border-red-500/40 bg-red-500/10 text-red-400',
  AWAITING_APPROVAL: 'border-orange-500/40 bg-orange-500/10 text-orange-400',
  RESOLVED: 'border-green-500/40 bg-green-500/10 text-green-400',
  RESOLVED_BY_AGENT: 'border-green-500/40 bg-green-500/10 text-green-400',
  REJECTED: 'border-slate-500/40 bg-slate-500/10 text-slate-400',
  ESCALATED_SECURITY_RISK: 'border-red-500/60 bg-red-500/15 text-red-400',
}

const TIMELINE_META = {
  detected: { label: 'Detected', cls: 'bg-slate-500' },
  triaged: { label: 'Triaged', cls: 'bg-blue-500' },
  actions_proposed: { label: 'Actions proposed', cls: 'bg-amber-500' },
  dry_run: { label: 'Dry-run', cls: 'bg-cyan-500' },
  approved: { label: 'Approved', cls: 'bg-green-500' },
  rejected: { label: 'Rejected', cls: 'bg-red-500' },
  executed: { label: 'Executed', cls: 'bg-emerald-500' },
  retriaged: { label: 'Re-triaged', cls: 'bg-violet-500' },
  agent_run: { label: 'Agent run', cls: 'bg-accent' },
  escalated: { label: 'Escalated', cls: 'bg-red-600' },
}

function commandRisk(cmd) {
  const c = String(cmd || '').toLowerCase()
  if (/rm\s+-rf|drop\s+table|delete\s+namespace|--force|destroy|format\s+/.test(c)) {
    return { level: 'high', cls: 'border-red-500/50 bg-red-500/10 text-red-400' }
  }
  if (/kubectl\s+delete|helm\s+uninstall|aws\s+.*delete|truncate|restart/.test(c)) {
    return { level: 'medium', cls: 'border-amber-500/50 bg-amber-500/10 text-amber-400' }
  }
  return { level: 'low', cls: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400' }
}

function formatTime(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return String(iso)
  }
}

function Skeleton() {
  return (
    <div className="flex flex-col gap-4 animate-pulse p-4 md:p-6 max-w-6xl mx-auto w-full">
      <div className="h-8 w-48 bg-card rounded-lg" />
      <div className="h-24 bg-card rounded-xl border border-border" />
      <div className="grid md:grid-cols-2 gap-4">
        <div className="h-64 bg-card rounded-xl border border-border" />
        <div className="h-64 bg-card rounded-xl border border-border" />
      </div>
      <div className="h-40 bg-card rounded-xl border border-border" />
    </div>
  )
}

function Timeline({ events }) {
  const list = Array.isArray(events) ? events : []
  if (!list.length) {
    return (
      <p className="text-xs text-slate-500 py-6 text-center">No timeline events yet.</p>
    )
  }
  return (
    <ol className="relative border-l border-border ml-3 space-y-4 py-1">
      {list.map((ev, idx) => {
        const meta = TIMELINE_META[ev.type] || { label: ev.type || 'Event', cls: 'bg-slate-500' }
        return (
          <li key={`${ev.type}-${ev.at}-${idx}`} className="ml-4 pl-1">
            <span
              className={`absolute -left-1.5 mt-1.5 w-3 h-3 rounded-full border border-surface ${meta.cls}`}
            />
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span className="text-xs font-semibold text-white">{meta.label}</span>
              <span className="text-[10px] text-slate-500">{formatTime(ev.at)}</span>
              {ev.actor && (
                <span className="text-[10px] text-slate-600">· {ev.actor}</span>
              )}
            </div>
            {ev.detail && (
              <p className="text-xs text-slate-400 mt-0.5 leading-relaxed break-words">
                {ev.detail}
              </p>
            )}
          </li>
        )
      })}
    </ol>
  )
}

export default function IncidentCommandCenter() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { authFetch, role } = useAuth()
  const { showToast } = useToast()

  const [incident, setIncident] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)
  const [rejectReason, setRejectReason] = useState('')
  const [copiedIdx, setCopiedIdx] = useState(null)
  const [postmortem, setPostmortem] = useState(null)
  const [postmortemEditing, setPostmortemEditing] = useState(false)
  const [postmortemDraft, setPostmortemDraft] = useState('')

  const loadPostmortem = useCallback(async () => {
    if (!id) return
    try {
      const res = await authFetch(`/api/incidents/${id}/postmortem`)
      if (res.status === 404) {
        setPostmortem(null)
        return
      }
      if (res.ok) {
        setPostmortem(await res.json())
      }
    } catch {
      setPostmortem(null)
    }
  }, [authFetch, id])

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const res = await authFetch(`/api/incidents/${id}`)
      if (res.status === 404) {
        setError('Incident not found')
        setIncident(null)
        return
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `Failed to load (${res.status})`)
      }
      setIncident(await res.json())
    } catch (e) {
      setError(e.message || 'Failed to load incident')
      setIncident(null)
    } finally {
      setLoading(false)
    }
  }, [authFetch, id])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    void loadPostmortem()
  }, [loadPostmortem])

  async function runAction(key, path, options = {}) {
    setBusy(key)
    try {
      const res = await authFetch(`/api/incidents/${id}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        ...options,
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        const detail =
          typeof data.detail === 'string'
            ? data.detail
            : data.detail?.message || JSON.stringify(data.detail || data)
        throw new Error(detail || `Request failed (${res.status})`)
      }
      if (data.incident) {
        setIncident(data.incident)
      } else if (data.timeline || data.id) {
        setIncident(data)
      } else if (data.new_incident?.id) {
        showToast(`Re-triage created incident #${data.new_incident.id}`, 'info')
        navigate(`/incidents/${data.new_incident.id}`)
        return
      } else {
        await load()
      }
      showToast(
        key === 'approve'
          ? 'Plan approved'
          : key === 'reject'
            ? 'Plan rejected'
            : key === 'agent'
              ? 'incident_agent finished'
              : 'Done',
        'success',
      )
    } catch (e) {
      showToast(e.message || 'Action failed', 'error')
    } finally {
      setBusy(null)
    }
  }

  function copyCmd(cmd, idx) {
    navigator.clipboard?.writeText(cmd).then(() => {
      setCopiedIdx(idx)
      setTimeout(() => setCopiedIdx(null), 1500)
    })
  }

  async function generatePostmortem() {
    setBusy('postmortem-generate')
    try {
      const res = await authFetch(`/api/incidents/${id}/postmortem/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(data.detail || `Generate failed (${res.status})`)
      }
      setPostmortem(data)
      setPostmortemDraft(data.markdown || '')
      setPostmortemEditing(false)
      showToast(`Postmortem v${data.version} generated`, 'success')
    } catch (e) {
      showToast(e.message || 'Postmortem generation failed', 'error')
    } finally {
      setBusy(null)
    }
  }

  async function savePostmortemEdit() {
    setBusy('postmortem-save')
    try {
      const res = await authFetch(`/api/incidents/${id}/postmortem`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ markdown: postmortemDraft }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(data.detail || `Save failed (${res.status})`)
      }
      setPostmortem(data)
      setPostmortemEditing(false)
      showToast('Postmortem saved', 'success')
    } catch (e) {
      showToast(e.message || 'Save failed', 'error')
    } finally {
      setBusy(null)
    }
  }

  async function downloadPostmortem() {
    setBusy('postmortem-download')
    try {
      const res = await authFetch(`/api/incidents/${id}/postmortem/download`)
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `Download failed (${res.status})`)
      }
      const blob = await res.blob()
      const version = postmortem?.version || 1
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `postmortem-incident-${id}-v${version}.md`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      showToast('Postmortem downloaded', 'success')
    } catch (e) {
      showToast(e.message || 'Download failed', 'error')
    } finally {
      setBusy(null)
    }
  }

  function startPostmortemEdit() {
    setPostmortemDraft(postmortem?.markdown || '')
    setPostmortemEditing(true)
  }

  if (loading) return <Skeleton />

  if (error || !incident) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 p-10 text-center max-w-lg mx-auto">
        <AlertCircle className="w-8 h-8 text-slate-500" />
        <p className="text-sm text-slate-300">{error || 'Incident not found'}</p>
        <Link
          to="/incidents"
          className="text-xs font-semibold text-accent hover:underline"
        >
          Back to incidents
        </Link>
      </div>
    )
  }

  const sev = SEVERITY_CFG[incident.severity] || SEVERITY_CFG.Unknown
  const SevIcon = sev.icon
  const status = (incident.status || 'OPEN').toUpperCase()
  const statusCls = STATUS_CLS[status] || STATUS_CLS.OPEN
  const awaiting = status === 'AWAITING_APPROVAL'
  const commands = Array.isArray(incident.commands) ? incident.commands : []
  const plan = Array.isArray(incident.action_plan)
    ? incident.action_plan
    : Array.isArray(incident.proposed_remediation_plan)
      ? incident.proposed_remediation_plan
      : []
  const gh = incident.github_refs || {}
  const pending = incident.pending_approval
  const execLog = incident.execution_log || incident.agent_execution_logs || incident.execution_logs

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6 max-w-6xl mx-auto w-full pb-16 animate-fade-in">
      {/* Back + refresh */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => navigate('/incidents')}
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Incidents
        </button>
        <button
          type="button"
          onClick={() => load()}
          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border text-xs text-slate-400 hover:text-white hover:bg-card transition-colors"
        >
          <RefreshCw className="w-3 h-3" />
          Refresh
        </button>
      </div>

      {/* Header */}
      <header className="rounded-xl border border-border bg-card/60 p-4 md:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg md:text-xl font-semibold text-white">
                Incident #{incident.id}
              </h1>
              <span
                className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border text-[10px] font-bold tracking-wider uppercase ${sev.cls}`}
              >
                <SevIcon className="w-3 h-3" strokeWidth={2.5} />
                {incident.severity || 'Unknown'}
              </span>
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded-md border text-[10px] font-bold tracking-wider uppercase ${statusCls}`}
              >
                {status.replace(/_/g, ' ')}
              </span>
            </div>
            <p className="text-sm text-slate-300 leading-relaxed">{incident.summary}</p>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
              <span className="inline-flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {formatTime(incident.timestamp)}
              </span>
              <span>
                Workspace:{' '}
                <span className="text-slate-400">
                  {incident.workspace_id || '—'}
                </span>
              </span>
              <span>
                Env:{' '}
                <span className="text-slate-400">
                  {incident.environment || 'production'}
                </span>
              </span>
              <span>
                Tenant:{' '}
                <span className="text-slate-400">{incident.tenant_id || 'default'}</span>
              </span>
              {incident.source && (
                <span>
                  Source: <span className="text-slate-400">{incident.source}</span>
                </span>
              )}
            </div>
          </div>
        </div>

        {(gh.repo || gh.pr_number || gh.run_id || gh.html_url) && (
          <div className="mt-3 pt-3 border-t border-border flex flex-wrap items-center gap-2 text-[11px]">
            <GitBranch className="w-3.5 h-3.5 text-slate-500" />
            {gh.repo && <span className="text-slate-400 font-mono">{gh.repo}</span>}
            {gh.pr_number != null && (
              <span className="text-slate-500">PR #{gh.pr_number}</span>
            )}
            {gh.run_id != null && (
              <span className="text-slate-500">Run {gh.run_id}</span>
            )}
            {gh.html_url && (
              <a
                href={gh.html_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-accent hover:underline"
              >
                GitHub <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        )}
      </header>

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        {awaiting && (
          <>
            <button
              type="button"
              disabled={!!busy}
              onClick={() =>
                runAction('approve', '/approve', {
                  body: JSON.stringify({
                    approved_by_role: role || 'Admin',
                  }),
                })
              }
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-green-500/40 bg-green-500/10 text-green-400 text-xs font-semibold hover:bg-green-500/20 disabled:opacity-50"
            >
              {busy === 'approve' ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="w-3.5 h-3.5" />
              )}
              Approve
            </button>
            <button
              type="button"
              disabled={!!busy}
              onClick={() =>
                runAction('reject', '/reject', {
                  body: JSON.stringify({
                    approved_by_role: role || 'Admin',
                    reason: rejectReason || 'plan rejected',
                  }),
                })
              }
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-red-500/40 bg-red-500/10 text-red-400 text-xs font-semibold hover:bg-red-500/20 disabled:opacity-50"
            >
              {busy === 'reject' ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <XCircle className="w-3.5 h-3.5" />
              )}
              Reject
            </button>
            <input
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Reject reason (optional)"
              className="flex-1 min-w-[160px] px-3 py-2 rounded-lg bg-surface border border-border text-xs text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-accent/50"
            />
          </>
        )}
        <button
          type="button"
          disabled={!!busy}
          onClick={() => runAction('retriage', '/retriage')}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border bg-card text-slate-300 text-xs font-semibold hover:bg-muted/40 disabled:opacity-50"
        >
          {busy === 'retriage' ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <RefreshCw className="w-3.5 h-3.5" />
          )}
          Re-run triage
        </button>
        <button
          type="button"
          disabled={!!busy}
          onClick={() => runAction('agent', '/run-agent')}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-accent/40 bg-accent/10 text-accent text-xs font-semibold hover:bg-accent/20 disabled:opacity-50"
        >
          {busy === 'agent' ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Bot className="w-3.5 h-3.5" />
          )}
          Run incident_agent
        </button>
        <button
          type="button"
          disabled={!!busy}
          onClick={() => runAction('dryrun', '/dry-run')}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-cyan-500/30 bg-cyan-500/5 text-cyan-400 text-xs font-semibold hover:bg-cyan-500/15 disabled:opacity-50"
        >
          {busy === 'dryrun' ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <ShieldAlert className="w-3.5 h-3.5" />
          )}
          Dry-run
        </button>
      </div>

      {pending && (
        <div className="rounded-lg border border-orange-500/30 bg-orange-500/5 px-4 py-3 text-xs text-orange-200/90">
          Pending approval for role{' '}
          <strong className="text-orange-300">{pending.owner_role}</strong>
          {pending.escalated && ' — escalated security risk'}
          {Array.isArray(pending.proposed_remediation_plan) &&
            pending.proposed_remediation_plan.length > 0 && (
              <span className="text-orange-400/80">
                {' '}
                · {pending.proposed_remediation_plan.length} step(s)
              </span>
            )}
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-4">
        {/* Timeline */}
        <section className="rounded-xl border border-border bg-card/40 p-4">
          <h2 className="text-sm font-semibold text-white mb-3">Timeline</h2>
          <Timeline events={incident.timeline} />
        </section>

        {/* AI summary + plan */}
        <section className="rounded-xl border border-border bg-card/40 p-4 space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-white mb-2">AI summary</h2>
            <p className="text-xs text-slate-400 leading-relaxed">
              {incident.root_cause || incident.summary || 'No summary available.'}
            </p>
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white mb-2">Action plan</h2>
            {plan.length === 0 ? (
              <p className="text-xs text-slate-500">No action plan recorded.</p>
            ) : (
              <ol className="list-decimal list-inside space-y-1.5">
                {plan.map((step, i) => (
                  <li key={i} className="text-xs text-slate-300 leading-relaxed">
                    {typeof step === 'string' ? step : JSON.stringify(step)}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </section>
      </div>

      {/* Commands */}
      <section className="rounded-xl border border-border bg-card/40 p-4">
        <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Terminal className="w-4 h-4 text-accent" />
          Commands
        </h2>
        {commands.length === 0 ? (
          <p className="text-xs text-slate-500">No commands proposed.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {commands.map((cmd, i) => {
              const risk = commandRisk(cmd)
              return (
                <li
                  key={i}
                  className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-lg border border-border bg-surface/80 px-3 py-2"
                >
                  <code className="flex-1 text-[11px] font-mono text-slate-300 break-all">
                    {cmd}
                  </code>
                  <div className="flex items-center gap-2 shrink-0">
                    <span
                      className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ${risk.cls}`}
                    >
                      {risk.level} risk
                    </span>
                    <button
                      type="button"
                      onClick={() => copyCmd(cmd, i)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded border border-border text-[10px] text-slate-400 hover:text-white hover:bg-card"
                      title="Copy"
                    >
                      <ClipboardCopy className="w-3 h-3" />
                      {copiedIdx === i ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {/* Execution log */}
      <section className="rounded-xl border border-border bg-card/40 p-4">
        <h2 className="text-sm font-semibold text-white mb-2">Execution log</h2>
        {execLog ? (
          <pre className="text-[11px] font-mono text-slate-400 whitespace-pre-wrap break-words bg-black/40 rounded-lg border border-border p-3 max-h-64 overflow-y-auto">
            {execLog}
          </pre>
        ) : (
          <p className="text-xs text-slate-500">No execution log yet. Approve a plan or run remediation to populate.</p>
        )}
      </section>

      {/* Postmortem */}
      <section className="rounded-xl border border-border bg-card/40 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-semibold text-white">Postmortem</h2>
            {postmortem?.version && (
              <span className="text-[10px] font-mono text-slate-500">v{postmortem.version}</span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => generatePostmortem()}
              disabled={!!busy}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-accent/40 bg-accent/10 text-xs font-semibold text-accent hover:bg-accent/20 disabled:opacity-50 transition-colors"
            >
              {busy === 'postmortem-generate' ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Bot className="w-3 h-3" />
              )}
              {postmortem ? 'Regenerate' : 'Generate'}
            </button>
            {postmortem && !postmortemEditing && (
              <>
                <button
                  type="button"
                  onClick={() => startPostmortemEdit()}
                  disabled={!!busy}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border text-xs text-slate-300 hover:text-white hover:bg-card disabled:opacity-50 transition-colors"
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => downloadPostmortem()}
                  disabled={!!busy}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border text-xs text-slate-300 hover:text-white hover:bg-card disabled:opacity-50 transition-colors"
                >
                  {busy === 'postmortem-download' ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Download className="w-3 h-3" />
                  )}
                  Download
                </button>
              </>
            )}
            {postmortemEditing && (
              <>
                <button
                  type="button"
                  onClick={() => savePostmortemEdit()}
                  disabled={!!busy}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-green-500/40 bg-green-500/10 text-xs font-semibold text-green-400 hover:bg-green-500/20 disabled:opacity-50 transition-colors"
                >
                  {busy === 'postmortem-save' ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <CheckCircle2 className="w-3 h-3" />
                  )}
                  Save
                </button>
                <button
                  type="button"
                  onClick={() => setPostmortemEditing(false)}
                  disabled={!!busy}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border text-xs text-slate-400 hover:text-white disabled:opacity-50 transition-colors"
                >
                  Cancel
                </button>
              </>
            )}
          </div>
        </div>
        {!postmortem && !postmortemEditing && (
          <p className="text-xs text-slate-500">
            Generate a structured postmortem from incident fields, timeline, triage, commands, and agent-run evidence.
          </p>
        )}
        {postmortemEditing && (
          <textarea
            value={postmortemDraft}
            onChange={(e) => setPostmortemDraft(e.target.value)}
            rows={16}
            className="w-full text-xs font-mono text-slate-300 bg-black/40 rounded-lg border border-border p-3 focus:outline-none focus:ring-1 focus:ring-accent/50 resize-y min-h-[12rem]"
            spellCheck={false}
          />
        )}
        {postmortem && !postmortemEditing && (
          <pre className="text-xs text-slate-300 whitespace-pre-wrap break-words bg-black/30 rounded-lg border border-border p-3 max-h-96 overflow-y-auto leading-relaxed">
            {postmortem.markdown}
          </pre>
        )}
      </section>
    </div>
  )
}
