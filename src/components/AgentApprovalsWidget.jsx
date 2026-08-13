import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  Bot, CheckCircle2, XCircle, Loader2, ShieldAlert,
  ChevronDown, ChevronUp, Clock, AlertTriangle, Terminal,
  Sparkles, ShieldX,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usePortalContext } from '../contexts/PortalContext'
import { usePortalWebSocket } from '../hooks/usePortalWebSocket'
import { useToast } from './ToastNotification'

const SEV_CFG = {
  Critical: { cls: 'bg-red-500/15 border-red-500/40 text-red-400',    dot: 'bg-red-400'    },
  High:     { cls: 'bg-orange-500/15 border-orange-500/40 text-orange-400', dot: 'bg-orange-400' },
  Warning:  { cls: 'bg-amber-500/15 border-amber-500/40 text-amber-400', dot: 'bg-amber-400' },
  Medium:   { cls: 'bg-yellow-500/15 border-yellow-500/40 text-yellow-400', dot: 'bg-yellow-400' },
}

function SevBadge({ severity }) {
  const cfg = SEV_CFG[severity] ?? { cls: 'bg-slate-500/15 border-slate-500/40 text-slate-400', dot: 'bg-slate-400' }
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg border text-[11px] font-bold uppercase ${cfg.cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {severity}
    </span>
  )
}

function SecurityRiskCard({ incident }) {
  const [expanded, setExpanded] = useState(false)
  const guardLogs = incident.agent_execution_logs ?? ''

  return (
    <div className="flex flex-col rounded-xl border border-red-500/50 bg-red-500/8 overflow-hidden">
      {/* Red warning banner */}
      <div className="flex items-center gap-2.5 px-4 py-3 bg-red-500/15 border-b border-red-500/30">
        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-red-500/20 border border-red-500/40 shrink-0">
          <ShieldX className="w-4 h-4 text-red-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-bold text-red-400 uppercase tracking-wide">
            AI Safety Guardrail Triggered
          </p>
          <p className="text-[11px] text-red-300 leading-snug mt-0.5">
            AI generated a potentially destructive command.
            <strong className="text-red-300"> Manual intervention required.</strong>
          </p>
        </div>
        <button
          onClick={() => setExpanded(v => !v)}
          className="p-1.5 rounded-lg hover:bg-red-500/20 text-red-500 hover:text-red-300 transition-colors shrink-0"
        >
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {/* Incident metadata */}
      <div className="flex items-start gap-3 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-xs font-bold text-white">Incident #{incident.id}</span>
            <Link
              to={`/incidents/${incident.id}`}
              className="text-[10px] font-semibold text-accent hover:underline"
            >
              Open command center
            </Link>
            <SevBadge severity={incident.severity} />
            <span className="text-[10px] text-red-500 font-bold uppercase tracking-widest border border-red-500/40 bg-red-500/10 px-2 py-0.5 rounded-full">
              ESCALATED — SECURITY RISK
            </span>
            <span className="text-[10px] text-slate-500 flex items-center gap-1">
              <Clock className="w-2.5 h-2.5" />
              {new Date(incident.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed">{incident.summary}</p>
        </div>
      </div>

      {/* Expandable guardrail log */}
      {expanded && guardLogs && (
        <div className="flex flex-col border-t border-red-500/20">
          <div className="flex items-center gap-2 px-4 py-2 bg-black/50 border-b border-red-500/15">
            <div className="flex gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
              <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/40" />
              <span className="w-2.5 h-2.5 rounded-full bg-green-500/40" />
            </div>
            <Terminal className="w-3 h-3 text-red-400" />
            <span className="text-[10px] font-mono text-red-400 font-semibold">guardrail-audit — incident-{incident.id}</span>
          </div>
          <pre className="px-4 py-3 bg-black text-[10px] font-mono text-red-400 leading-relaxed overflow-x-auto whitespace-pre max-h-40 overflow-y-auto">
            {guardLogs}
          </pre>
        </div>
      )}

      {/* Footer instruction */}
      <div className="px-4 py-2.5 border-t border-red-500/20 flex items-center gap-2 text-[11px] text-red-400/80">
        <ShieldAlert className="w-3.5 h-3.5 shrink-0 text-red-500" />
        Review the guardrail log above and remediate manually. Proposed plan has been cleared.
      </div>
    </div>
  )
}


function AIHitlExecutionCard({ ex, onRemoved, authFetch, refreshApprovals, showToast }) {
  const [busy, setBusy] = useState(false)
  const [showReject, setShowReject] = useState(false)
  const [reason, setReason] = useState('')
  const ctx = ex.conversation_context
  const env = ex.environment || ctx?.environment || '—'
  const prod = String(env).toLowerCase() === 'production'
  const status = ex.status || 'pending_approval'
  const requiresHitl = ex.requires_hitl !== false

  async function approve() {
    setBusy(true)
    try {
      const res = await authFetch(`/api/ai/executions/${encodeURIComponent(ex.id)}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved_by: 'admin' }),
      })
      if (!res.ok) throw new Error(await res.text())
      showToast('Execution approved', 'success')
      onRemoved(ex.id)
      await refreshApprovals()
    } catch (e) {
      showToast(e.message || 'Approve failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function reject() {
    setBusy(true)
    try {
      const res = await authFetch(`/api/ai/executions/${encodeURIComponent(ex.id)}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rejected_by: 'admin', reason: reason || '' }),
      })
      if (!res.ok) throw new Error(await res.text())
      showToast('Execution rejected', 'success')
      setShowReject(false)
      setReason('')
      onRemoved(ex.id)
      await refreshApprovals()
    } catch (e) {
      showToast(e.message || 'Reject failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col rounded-xl border border-violet-500/25 bg-violet-500/5 overflow-hidden">
      <div className="flex items-start justify-between gap-3 px-4 py-3 border-b border-violet-500/15">
        <div className="flex items-start gap-3 min-w-0">
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-violet-500/15 border border-violet-500/30 shrink-0">
            <Bot className="w-4 h-4 text-violet-400" />
          </div>
          <div className="min-w-0">
            <p className="text-[10px] font-bold text-violet-400 uppercase tracking-wide">AI Assistant — HITL</p>
            <p className="text-xs font-semibold text-white mt-0.5">
              {ex.tool_id} → {ex.action}
            </p>
            <div className="flex flex-wrap gap-2 mt-1.5">
              <span
                className={`text-[10px] px-2 py-0.5 rounded-md border font-semibold uppercase ${
                  prod
                    ? 'border-red-500/50 text-red-200 bg-red-950/40'
                    : 'border-slate-600 text-slate-400'
                }`}
              >
                {env}
              </span>
              {requiresHitl && (
                <span className="text-[10px] px-2 py-0.5 rounded-md border border-amber-500/40 text-amber-200 bg-amber-950/40 font-semibold uppercase">
                  requires HITL
                </span>
              )}
              <span className="text-[10px] px-2 py-0.5 rounded-md border border-violet-500/30 text-violet-200 bg-violet-950/30 font-mono">
                {status}
              </span>
              {ctx?.title && (
                <span className="text-[10px] text-slate-500 truncate max-w-[200px]" title={ctx.title}>
                  {ctx.title}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
      <div className="px-4 py-3 flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => void approve()}
            className="flex-1 min-w-[100px] flex items-center justify-center gap-2 py-2 rounded-lg bg-emerald-600/20 border border-emerald-500/40 text-emerald-300 text-xs font-bold hover:bg-emerald-600/30 disabled:opacity-40"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
            Approve
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setShowReject((v) => !v)}
            className="flex-1 min-w-[100px] flex items-center justify-center gap-2 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-bold hover:bg-red-500/20 disabled:opacity-40"
          >
            <XCircle className="w-3.5 h-3.5" /> Reject
          </button>
        </div>
        {showReject && (
          <div className="flex flex-col gap-2 pt-1">
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason (optional)"
              className="text-xs px-2 py-1.5 rounded-lg bg-slate-950 border border-border text-white"
            />
            <button
              type="button"
              disabled={busy}
              onClick={() => void reject()}
              className="text-xs text-red-300 font-semibold self-start"
            >
              Confirm reject
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function ApprovalCard({ incident, onApprove, onReject }) {
  const { role } = useAuth()
  const { authFetch } = useAuth()
  const [expanded,  setExpanded]  = useState(false)
  const [approving, setApproving] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [execLogs,  setExecLogs]  = useState(null)
  const [done,      setDone]      = useState(false)
  const [rejected,  setRejected]  = useState(false)
  const [showDryRun, setShowDryRun] = useState(false);
  const [dryRunResult, setDryRunResult] = useState(null);

  const canAct = role === 'Admin' || role === incident.owner_role

  async function handleApprove() {
    setApproving(true)
    try {
      const res = await authFetch(`/api/incidents/${incident.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved_by_role: role }),
      })
      const data = await res.json()
      setExecLogs(data.agent_execution_logs)
      setDone(true)
      onApprove?.(incident.id)
    } catch (_) {}
    finally { setApproving(false) }
  }

  async function handleReject() {
    setRejecting(true)
    try {
      await authFetch(`/api/incidents/${incident.id}/reject`, { method: 'POST' })
      setRejected(true)
      onReject?.(incident.id)
    } catch (_) {}
    finally { setRejecting(false) }
  }

  const plan = incident.proposed_remediation_plan ?? []

  return (
    <div className={`flex flex-col rounded-xl border overflow-hidden transition-all
      ${done    ? 'border-green-500/25 bg-green-500/5'
      : rejected ? 'border-slate-700   bg-slate-900/30 opacity-60'
      : 'border-orange-500/25 bg-orange-500/5'}`}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 px-4 py-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-orange-500/15 border border-orange-500/30 shrink-0 mt-0.5">
            <Bot className="w-4 h-4 text-orange-400" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className="text-xs font-bold text-white">Incident #{incident.id}</span>
              <Link
                to={`/incidents/${incident.id}`}
                className="text-[10px] font-semibold text-accent hover:underline"
              >
                Command center
              </Link>
              <SevBadge severity={incident.severity} />
              <span className="text-[10px] text-slate-500 flex items-center gap-1">
                <Clock className="w-2.5 h-2.5" />
                {new Date(incident.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed line-clamp-2">{incident.summary}</p>
          </div>
        </div>

        <button
          onClick={() => setExpanded(v => !v)}
          className="p-1.5 rounded-lg hover:bg-white/5 text-slate-500 hover:text-slate-300 transition-colors shrink-0"
        >
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {/* Expanded: plan + buttons */}
      {expanded && !done && !rejected && (
        <div className="px-4 pb-4 flex flex-col gap-3 border-t border-orange-500/15 pt-3">
          {/* Proposed plan */}
          {plan.length > 0 && (
            <div className="flex flex-col gap-2">
              <p className="text-[10px] font-bold text-orange-400 uppercase tracking-widest flex items-center gap-1.5">
                <Sparkles className="w-3 h-3" /> AI Proposed Remediation Plan
              </p>
              <ol className="flex flex-col gap-1.5">
                {plan.map((step, i) => {
                  const isCode = step.startsWith('--') || step.startsWith('SELECT') ||
                    step.startsWith('UPDATE') || step.startsWith('DELETE') ||
                    step.startsWith('ALTER') || step.startsWith('VACUUM') ||
                    step.startsWith('sudo') || step.startsWith('psql') ||
                    step.startsWith('pg_') || step.startsWith('SHOW')
                  return isCode ? (
                    <li key={i}>
                      <pre className="text-[10px] font-mono text-green-400 bg-black/60 border border-green-500/20
                        rounded-lg px-3 py-2 overflow-x-auto whitespace-pre leading-relaxed">
                        {step}
                      </pre>
                    </li>
                  ) : (
                    <li key={i} className="flex items-start gap-2 text-xs text-slate-300">
                      <span className="w-4 h-4 rounded-full bg-orange-500/20 border border-orange-500/30 text-orange-400
                        text-[9px] font-bold flex items-center justify-center shrink-0 mt-0.5">
                        {i + 1}
                      </span>
                      <span className="leading-relaxed">{step}</span>
                    </li>
                  )
                })}
              </ol>
            </div>
          )}

          {/* RBAC guard */}
          {!canAct ? (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-red-500/20 bg-red-500/5 text-xs text-red-400">
              <ShieldAlert className="w-3.5 h-3.5 shrink-0" />
              Only <strong>{incident.owner_role}</strong> or Admin can approve this incident.
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={async () => {
                  const res = await authFetch(`/api/incidents/${incident.id}/dry-run`, {
                    method: "POST",
                  });
                  const data = await res.json();
                  setDryRunResult(data);
                  setShowDryRun(true);
                }}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium mr-2"
              >
                🔍 Dry Run
              </button>
              <button
                onClick={handleApprove}
                disabled={approving || rejecting}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl
                  bg-green-500/15 border border-green-500/35 text-green-400 text-xs font-bold
                  hover:bg-green-500/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {approving
                  ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Executing…</>
                  : <><CheckCircle2 className="w-3.5 h-3.5" /> Approve Execution</>
                }
              </button>
              <button
                onClick={handleReject}
                disabled={approving || rejecting}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl
                  bg-red-500/10 border border-red-500/30 text-red-400 text-xs font-bold
                  hover:bg-red-500/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {rejecting
                  ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Rejecting…</>
                  : <><XCircle className="w-3.5 h-3.5" /> Reject</>
                }
              </button>
            </div>
          )}

          {showDryRun && dryRunResult && (
            <div className="mt-4 p-4 bg-gray-900 rounded-lg border border-blue-500">
              <div className="flex justify-between items-center mb-2">
                <h4 className="text-blue-400 font-semibold">🔍 Dry Run Preview</h4>
                <span className={`text-xs px-2 py-1 rounded ${dryRunResult.all_safe ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"}`}>
                  {dryRunResult.all_safe ? "✅ All Safe" : "⚠️ Issues Detected"}
                </span>
              </div>
              {dryRunResult.steps?.map((step, i) => (
                <div key={i} className="mb-2 text-sm font-mono">
                  <span className={step.safe ? "text-green-400" : "text-red-400"}>
                    {step.safe ? "✅" : "❌"} Step {i+1}: {step.command}
                  </span>
                  {!step.safe && (
                    <div className="text-red-300 text-xs ml-4">
                      Violations: {step.violations.join(", ")}
                    </div>
                  )}
                </div>
              ))}
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => { setShowDryRun(false); handleApprove(); }}
                  disabled={!dryRunResult.all_safe}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded text-sm"
                >
                  ✅ Looks Good — Approve
                </button>
                <button onClick={() => setShowDryRun(false)} className="px-4 py-2 bg-gray-600 text-white rounded text-sm">
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Post-approval: terminal output */}
      {done && execLogs && (
        <div className="border-t border-green-500/20 flex flex-col">
          <div className="flex items-center gap-2 px-4 py-2 bg-black/40 border-b border-green-500/15">
            <div className="flex gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
              <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
              <span className="w-2.5 h-2.5 rounded-full bg-green-500/60" />
            </div>
            <Terminal className="w-3 h-3 text-green-400" />
            <span className="text-[10px] font-mono text-green-400 font-semibold">agent-runbook — incident-{incident.id}</span>
            <span className="ml-auto flex items-center gap-1 text-[10px] text-green-500">
              <CheckCircle2 className="w-3 h-3" /> RESOLVED BY AGENT
            </span>
          </div>
          <pre className="px-4 py-3 bg-black text-[10px] font-mono text-green-400 leading-relaxed overflow-x-auto whitespace-pre max-h-36 overflow-y-auto">
            {execLogs}
          </pre>
        </div>
      )}

      {/* Rejected state */}
      {rejected && (
        <div className="px-4 py-2.5 border-t border-slate-700 flex items-center gap-2 text-xs text-slate-500">
          <XCircle className="w-3.5 h-3.5 text-red-500/60" />
          Execution rejected — incident remains open for manual review.
        </div>
      )}
    </div>
  )
}

function AgentPipelineApprovalCard({ run, authFetch, onDone, toast }) {
  const [busy, setBusy] = useState(false)
  const [resultUrl, setResultUrl] = useState(null)
  const [confirmText, setConfirmText] = useState('')
  const details = run.details || {}
  const payload = run.approval_payload || {}
  const preview = details.preview || payload.preview || null
  const isArtifact = details.source === 'artifact' || Boolean(payload.artifact_approval_id)
  const grounding = details.grounding || preview?.grounding || '—'
  const connector = details.connector || payload.connector
  const method = details.method || payload.method
  const destroyCount = Number(preview?.destroy_count || 0)
  const requireTyped =
    Boolean(preview?.require_typed_confirm) || destroyCount > 0
  const confirmPhrase = String(preview?.confirm_phrase || preview?.workspace || '')
  const typedOk = !requireTyped || confirmText.trim() === confirmPhrase
  const blast = preview?.blast_radius
  const isTf = preview?.type === 'terraform_plan'
  const isMig = preview?.type === 'sql_migration'
  const isSec = preview?.type === 'security_remediation'
  const isCost = preview?.type === 'cost_rightsizing'
  const isPd = preview?.type === 'pagerduty_override' || preview?.type === 'pagerduty_escalation'
  const isAccess = preview?.type === 'access_request' || connector === 'okta' || connector === 'access'
  const isChange = preview?.type === 'change_record' || connector === 'change'
  const isCompliance = preview?.type === 'compliance_evidence_pack' || connector === 'compliance'

  async function approve() {
    if (!typedOk) {
      toast.error(`Type the workspace name "${confirmPhrase}" to approve`)
      return
    }
    setBusy(true)
    try {
      const res = await authFetch(`/api/agents/${run.run_id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requireTyped ? { confirmation: confirmText.trim() } : {}),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(typeof body === 'string' ? body : (body.detail || JSON.stringify(body)))
      if (body?.status === 'pending_approval') {
        toast.info(body?.execution_log ? String(body.execution_log).slice(0, 160) : 'Awaiting additional approval')
        onDone(run.run_id)
        return
      }
      const url =
        body?.execution_log && String(body.execution_log).includes('url')
          ? (() => {
              try {
                const parsed = JSON.parse(body.execution_log)
                return parsed.url || parsed.pr_url || parsed.html_url || null
              } catch {
                return null
              }
            })()
          : null
      if (url) setResultUrl(url)
      toast.success(url ? `Approved — ${url}` : 'Agent run approved')
      onDone(run.run_id)
    } catch (e) {
      toast.error(e.message || 'Approve failed')
    } finally {
      setBusy(false)
    }
  }

  async function reject() {
    setBusy(true)
    try {
      const res = await authFetch(`/api/agents/${run.run_id}/reject`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      toast.success('Agent run rejected')
      onDone(run.run_id)
    } catch (e) {
      toast.error(e.message || 'Reject failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-violet-500/30 bg-violet-500/5 p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="text-xs font-bold text-violet-300 uppercase">{run.agent}</span>
        <span className="text-[10px] text-slate-500">{run.environment}</span>
      </div>
      <p className="text-sm text-slate-200">{run.summary}</p>
      {isArtifact ? (
        <div className="rounded-lg border border-slate-700/80 bg-slate-950/50 p-3 space-y-2">
          <div className="flex flex-wrap gap-2 text-[10px]">
            <span className="rounded border border-slate-600 px-2 py-0.5 text-slate-300">
              {connector}.{method}
            </span>
            <span className="rounded border border-emerald-500/40 px-2 py-0.5 text-emerald-300">
              grounding: {grounding}
            </span>
            {destroyCount > 0 ? (
              <span className="rounded border border-red-500/50 px-2 py-0.5 text-red-300 font-bold">
                DESTROY {destroyCount}
              </span>
            ) : null}
            {preview?.approvals_required > 1 ? (
              <span className="rounded border border-amber-500/40 px-2 py-0.5 text-amber-200">
                needs {preview.approvals_required} approvers
              </span>
            ) : null}
          </div>
          {isTf ? (
            <div className="space-y-1 text-[11px] text-slate-300">
              <p>Workspace: <span className="font-mono text-white">{preview.workspace}</span></p>
              <p>+{preview.resources_to_add?.length || 0} ~{preview.resources_to_change?.length || 0} -{destroyCount}</p>
              {preview.plan_text ? (
                <pre className="text-[10px] font-mono text-slate-400 whitespace-pre-wrap max-h-40 overflow-auto">{preview.plan_text}</pre>
              ) : null}
            </div>
          ) : null}
          {isMig ? (
            <div className="space-y-1 text-[11px] text-slate-300">
              <p>Shadow: {preview.shadow_run?.success ? 'ok' : 'FAILED'} · rows {preview.estimated_row_impact ?? '—'}</p>
              <p>Rollback: {preview.reversible ? 'yes' : 'manual / missing'}</p>
              <pre className="text-[10px] font-mono text-slate-400 whitespace-pre-wrap max-h-28 overflow-auto">{preview.forward_sql}</pre>
              <pre className="text-[10px] font-mono text-slate-500 whitespace-pre-wrap max-h-20 overflow-auto">{preview.rollback_sql}</pre>
            </div>
          ) : null}
          {isSec && blast ? (
            <div className="rounded border border-amber-500/30 bg-amber-950/20 p-2 text-[11px] text-amber-100 space-y-1">
              <p className="font-semibold">Blast radius</p>
              <p>{blast.risk_note}</p>
              <p className="font-mono text-[10px] text-amber-200/80">{(blast.affected_resources || []).join(', ')}</p>
              {preview.instances_using_sg?.length ? (
                <p>Instances: {preview.instances_using_sg.join(', ')}</p>
              ) : null}
            </div>
          ) : null}
          {isCost ? (
            <div className="text-[11px] text-slate-300 space-y-1">
              <p>{preview.instance_id}: {preview.current_type} → {preview.proposed_type}</p>
              <p>Saving ~${preview.projected_monthly_saving}/mo · mode {preview.mode}</p>
            </div>
          ) : null}
          {isPd ? (
            <div className="text-[11px] text-slate-300">
              <pre className="text-[10px] font-mono text-slate-400 whitespace-pre-wrap max-h-32 overflow-auto">
                {JSON.stringify(preview, null, 2)}
              </pre>
            </div>
          ) : null}
          {isAccess ? (
            <div className="text-[11px] text-slate-300 space-y-1">
              <p>Subject: <span className="font-mono text-white">{preview?.subject_username || '—'}</span></p>
              <p>Resource: <span className="font-mono text-white">{preview?.resource_type}:{preview?.resource_id}</span></p>
              <p>
                Owner: <span className="font-mono text-white">{preview?.owner_username || '—'}</span>
                {preview?.owner_missing ? (
                  <span className="ml-2 text-red-300">[NO OWNER — routed to admin]</span>
                ) : null}
              </p>
              {preview?.duration_hours ? (
                <p>Duration: {preview.duration_hours}h (auto-expires)</p>
              ) : null}
            </div>
          ) : null}
          {isChange ? (
            <div className="text-[11px] text-slate-300 space-y-1">
              <p>Change type: <span className="font-mono text-white">{preview?.change_type}</span> · risk {preview?.risk}</p>
              <p>Dependents: {preview?.blast_radius?.dependent_count ?? 0}</p>
              {preview?.rollback_plan ? (
                <pre className="text-[10px] font-mono text-slate-400 whitespace-pre-wrap max-h-20 overflow-auto">{preview.rollback_plan}</pre>
              ) : null}
            </div>
          ) : null}
          {isCompliance ? (
            <div className="text-[11px] text-slate-300 space-y-1">
              <p className="text-amber-200 font-semibold">
                Evidence pack — sensitive, HITL required
              </p>
              <p>Period: {preview?.period_start} → {preview?.period_end}</p>
              <p>Controls: {Object.keys(preview?.controls || {}).length}</p>
            </div>
          ) : null}
          {!isTf && !isMig && !isSec && !isCost && !isPd && !isAccess && !isChange && !isCompliance && preview ? (
            <pre className="text-[10px] font-mono text-slate-400 whitespace-pre-wrap max-h-48 overflow-auto">
              {typeof preview === 'string' ? preview : JSON.stringify(preview, null, 2)}
            </pre>
          ) : null}
          {requireTyped ? (
            <div className="space-y-1">
              <label className="text-[10px] text-red-300 font-semibold">
                Type workspace name &quot;{confirmPhrase}&quot; to enable Approve
              </label>
              <input
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                className="w-full rounded-md border border-red-500/40 bg-slate-900 px-2 py-1.5 text-xs text-white font-mono"
                placeholder={confirmPhrase}
                autoComplete="off"
              />
            </div>
          ) : null}
        </div>
      ) : null}
      {resultUrl ? (
        <a
          href={resultUrl}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-indigo-300 hover:text-indigo-200 underline"
        >
          Open artifact
        </a>
      ) : null}
      <p className="text-[10px] text-slate-500">
        By {run.triggered_by} · {run.timestamp ? new Date(run.timestamp).toLocaleString() : '—'}
      </p>
      <div className="flex gap-2 mt-1">
        <button
          type="button"
          disabled={busy || !typedOk}
          onClick={() => void approve()}
          className="flex-1 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold disabled:opacity-50"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void reject()}
          className="flex-1 py-2 rounded-lg border border-slate-600 text-slate-300 text-xs font-semibold hover:bg-slate-800 disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  )
}

export default function AgentApprovalsWidget({ roleFilter = null }) {
  const { role } = useAuth()
  const { authFetch, user } = useAuth()
  const { refreshApprovals } = usePortalContext()
  const { toast } = useToast()
  const showToast = (msg, type) => {
    if (type === 'error') toast.error(msg)
    else if (type === 'warning') toast.warning(msg)
    else if (type === 'info') toast.info(msg)
    else toast.success(msg)
  }
  // roleFilter prop pins the widget to a specific role regardless of the active persona.
  const effectiveRole = roleFilter ?? role

  const [incidents, setIncidents] = useState([])
  const [aiPending, setAiPending] = useState([])
  const [agentRuns, setAgentRuns] = useState([])
  const [loading, setLoading] = useState(true)

  const securityRiskCount = incidents.filter((i) => i.status === 'ESCALATED_SECURITY_RISK').length
  const approvalCount = incidents.filter((i) => i.status === 'AWAITING_APPROVAL').length
  const aiPendingCount = aiPending.length
  const pipelineApprovalCount = agentRuns.length

  const fetchAll = useCallback(async () => {
    try {
      const param = effectiveRole === 'Admin' ? '' : `?role=${effectiveRole}`
      const res = await authFetch(`/api/incidents/approvals${param}`)
      if (res.ok) setIncidents(await res.json())
      else setIncidents([])

      if (effectiveRole === 'Admin') {
        const ar = await authFetch('/api/ai/executions/pending')
        if (ar.ok) setAiPending(await ar.json())
        else setAiPending([])

        const pr = await authFetch('/api/agents/approvals')
        if (pr.ok) setAgentRuns(await pr.json())
        else setAgentRuns([])
      } else {
        setAiPending([])
        setAgentRuns([])
      }
    } catch {
      setIncidents([])
      setAiPending([])
      setAgentRuns([])
    } finally {
      setLoading(false)
    }
  }, [effectiveRole, authFetch])

  useEffect(() => {
    setLoading(true)
    void fetchAll()
    const t = setInterval(() => void fetchAll(), 10000)
    return () => clearInterval(t)
  }, [fetchAll])

  usePortalWebSocket({
    userId: user?.username || 'anonymous',
    onMessage: useCallback(
      (msg) => {
        if (msg.type === 'approval_update') {
          void fetchAll()
          void refreshApprovals()
        }
      },
      [fetchAll, refreshApprovals]
    ),
  })

  function removeIncident(id) {
    setIncidents((prev) => prev.filter((i) => i.id !== id))
  }

  function removeAiExecution(id) {
    setAiPending((prev) => prev.filter((x) => x.id !== id))
  }

  function removeAgentRun(runId) {
    setAgentRuns((prev) => prev.filter((r) => r.run_id !== runId))
  }

  if (loading) return (
    <div className="flex items-center gap-2 px-4 py-6 text-slate-500 text-xs">
      <Loader2 className="w-4 h-4 animate-spin text-accent" /> Loading agent approvals…
    </div>
  )

  return (
    <div className="flex flex-col gap-3 p-5 rounded-2xl border border-orange-500/20 bg-orange-500/5">
      {/* Widget header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-orange-500/15 border border-orange-500/30 shrink-0">
            <Bot className="w-4.5 h-4.5 text-orange-400" />
          </div>
          <div>
            <p className="text-sm font-bold text-white flex items-center gap-2 flex-wrap">
              Agent Pending Approvals
              {aiPendingCount > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-violet-600 text-white text-[10px] font-bold">
                  AI {aiPendingCount}
                </span>
              )}
              {securityRiskCount > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full
                  bg-red-500 text-white text-[10px] font-bold animate-pulse">
                  <ShieldX className="w-2.5 h-2.5" />{securityRiskCount} risk
                </span>
              )}
              {approvalCount > 0 && (
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full
                  bg-orange-500 text-white text-[10px] font-bold">
                  {approvalCount}
                </span>
              )}
            </p>
            <p className="text-[10px] text-slate-500">
              HITL queue for <span className="text-orange-400 font-semibold">{effectiveRole}</span> — incidents and AI tool actions awaiting approval
            </p>
          </div>
        </div>
        {securityRiskCount > 0 && (
          <span className="flex items-center gap-1.5 text-[11px] text-red-400 border border-red-500/30 bg-red-500/10 px-2.5 py-1 rounded-full font-semibold">
            <ShieldX className="w-3 h-3" /> {securityRiskCount} security risk
          </span>
        )}
        {approvalCount > 0 && (
          <span className="flex items-center gap-1.5 text-[11px] text-orange-400 border border-orange-500/25 bg-orange-500/10 px-2.5 py-1 rounded-full font-semibold">
            <AlertTriangle className="w-3 h-3" /> {approvalCount} pending
          </span>
        )}
      </div>

      {incidents.length === 0 && aiPending.length === 0 && agentRuns.length === 0 ? (
        <div className="flex items-center gap-2 px-4 py-5 rounded-xl border border-dashed border-slate-700 text-slate-600 text-xs justify-center">
          <CheckCircle2 className="w-4 h-4 text-green-600" />
          No incidents or AI actions awaiting approval — queue is clear.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {agentRuns.map((run) => (
            <AgentPipelineApprovalCard
              key={run.run_id}
              run={run}
              authFetch={authFetch}
              onDone={removeAgentRun}
              toast={toast}
            />
          ))}
          {aiPending.map((ex) => (
            <AIHitlExecutionCard
              key={ex.id}
              ex={ex}
              onRemoved={removeAiExecution}
              authFetch={authFetch}
              refreshApprovals={refreshApprovals}
              showToast={showToast}
            />
          ))}
          {incidents.map((inc) =>
            inc.status === 'ESCALATED_SECURITY_RISK' ? (
              <SecurityRiskCard key={inc.id} incident={inc} />
            ) : (
              <ApprovalCard
                key={inc.id}
                incident={inc}
                onApprove={removeIncident}
                onReject={removeIncident}
              />
            )
          )}
        </div>
      )}
    </div>
  )
}
