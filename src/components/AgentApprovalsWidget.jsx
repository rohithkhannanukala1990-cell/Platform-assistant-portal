import { useEffect, useState, useCallback } from 'react'
import {
  Bot, CheckCircle2, XCircle, Loader2, ShieldAlert,
  ChevronDown, ChevronUp, Clock, AlertTriangle, Terminal,
  Sparkles, ShieldX,
} from 'lucide-react'
import { useRole } from '../contexts/RoleContext'
import { useAuth } from '../contexts/AuthContext'

const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

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


function ApprovalCard({ incident, onApprove, onReject }) {
  const { role } = useRole()
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
      const res = await fetch(`${BASE}/api/incidents/${incident.id}/approve`, {
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
      await fetch(`${BASE}/api/incidents/${incident.id}/reject`, { method: 'POST' })
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
                  onClick={() => { setShowDryRun(false); handleApprove(incident.id); }}
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

export default function AgentApprovalsWidget({ roleFilter = null }) {
  const { role } = useRole()
  // roleFilter prop pins the widget to a specific role regardless of the active persona.
  // e.g. DatabasePortal passes roleFilter="DatabaseDeveloper" so it always shows DB incidents.
  const effectiveRole = roleFilter ?? role

  const [incidents,  setIncidents]  = useState([])
  const [loading,    setLoading]    = useState(true)

  const securityRiskCount = incidents.filter(i => i.status === 'ESCALATED_SECURITY_RISK').length
  const approvalCount     = incidents.filter(i => i.status === 'AWAITING_APPROVAL').length

  const fetchApprovals = useCallback(async () => {
    try {
      const param = effectiveRole === 'Admin' ? '' : `?role=${effectiveRole}`
      const res   = await fetch(`${BASE}/api/incidents/approvals${param}`)
      if (res.ok) setIncidents(await res.json())
    } catch (_) {}
    finally { setLoading(false) }
  }, [effectiveRole])

  useEffect(() => {
    fetchApprovals()
    const t = setInterval(fetchApprovals, 10000)
    return () => clearInterval(t)
  }, [fetchApprovals])

  function removeIncident(id) {
    setIncidents(prev => prev.filter(i => i.id !== id))
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
            <p className="text-sm font-bold text-white flex items-center gap-2">
              Agent Pending Approvals
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
              HITL queue for <span className="text-orange-400 font-semibold">{effectiveRole}</span> — HIGH/CRITICAL incidents awaiting your approval
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

      {incidents.length === 0 ? (
        <div className="flex items-center gap-2 px-4 py-5 rounded-xl border border-dashed border-slate-700 text-slate-600 text-xs justify-center">
          <CheckCircle2 className="w-4 h-4 text-green-600" />
          No incidents awaiting approval — agent queue is clear.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {incidents.map(inc =>
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
