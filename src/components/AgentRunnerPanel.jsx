import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Bot, Loader2, Play, RotateCcw,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usePlatformContext } from '../contexts/PlatformContext'
import { useToast } from './ToastNotification'
import { API_BASE } from '../config/apiBase'
import { parseApiError } from '../utils/parseApiError'
import { AgentApproveRejectButtons, GroundingBadge } from './agent/AgentRunBadges'
import AgentRunHistory from './AgentRunHistory'

const AGENT_NAMES = [
  'deploy_agent',
  'security_agent',
  'tester_agent',
  'infra_agent',
  'incident_agent',
  'cost_agent',
  'code_review_agent',
  'runbook_agent',
  'catalog_health_agent',
  'pipeline_monitor_agent',
  'auto_heal_agent',
  'onboarding_agent',
  'documentation_agent',
  'scorecard_agent',
  'dependency_drift_agent',
  'alert_noise_agent',
  'migration_agent',
]

const TERMINAL_STATUSES = new Set(['success', 'failed', 'pending_approval', 'skipped', 'dry_run', 'error', 'rejected'])

function buildAgentRunWsUrl(runId, token) {
  const qs = `token=${encodeURIComponent(token || '')}`
  if (API_BASE) {
    try {
      const u = new URL(API_BASE.startsWith('http') ? API_BASE : `http://${API_BASE}`)
      u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
      u.pathname = `/ws/agent-run/${runId}`
      u.search = qs
      u.hash = ''
      return u.toString()
    } catch {
      /* fall through */
    }
  }
  const proto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = typeof window !== 'undefined' ? window.location.host : 'localhost:8000'
  return `${proto}://${host}/ws/agent-run/${runId}?${qs}`
}

function parseMultiAgentCards(result, selectedAgents) {
  const cards = []

  if (result.approval_payload?.agents?.length) {
    for (const sub of result.approval_payload.agents) {
      cards.push({
        agent: sub.agent,
        run_id: sub.run_id,
        status: sub.status,
        summary: sub.summary,
        grounding: sub.grounding,
        evidence: sub.evidence,
        policy: sub.policy,
        startedAt: Date.now(),
      })
    }
    return cards
  }

  if (result.agent === 'orchestrator' && result.details && typeof result.details === 'object') {
    const agents = selectedAgents.length ? selectedAgents : Object.keys(result.details)
    const summaryParts = String(result.summary || '').split('|').map((s) => s.trim())

    for (const name of agents) {
      let status = result.status
      let summary = result.summary
      const part = summaryParts.find((p) => p.startsWith(`[${name}]`))
      if (part) {
        summary = part.replace(`[${name}]`, '').trim()
        if (result.status === 'failed') status = 'failed'
        else if (result.status === 'pending_approval') status = 'pending_approval'
        else if (result.status === 'skipped') status = 'skipped'
        else status = 'success'
      }
      cards.push({
        agent: name,
        run_id: result.run_id,
        status,
        summary,
        grounding: result.grounding,
        evidence: result.evidence,
        policy: result.policy,
        startedAt: Date.now(),
      })
    }
    return cards
  }

  return [{
    agent: result.agent,
    run_id: result.run_id,
    status: result.status,
    summary: result.summary,
    grounding: result.grounding,
    evidence: result.evidence,
    policy: result.policy,
    startedAt: Date.now(),
  }]
}

function ElapsedTimer({ running, startedAt }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!running || !startedAt) return undefined
    const tick = () => setElapsed(Math.floor((Date.now() - startedAt) / 1000))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [running, startedAt])

  if (!running) return null

  const m = Math.floor(elapsed / 60)
  const s = elapsed % 60
  return (
    <span className="text-[11px] font-mono text-blue-400 tabular-nums">
      {m}:{String(s).padStart(2, '0')}
    </span>
  )
}

function AgentRunCard({ card, onApprove, onReject, busy }) {
  const running = card.status === 'running'
  const pending = card.status === 'pending_approval'
  const noData = card.status === 'skipped' || card.grounding === 'none'
  const [showEvidence, setShowEvidence] = useState(false)
  const evidence = Array.isArray(card.evidence) ? card.evidence : []

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-indigo-500/15 border border-indigo-500/30 shrink-0">
            {running ? (
              <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />
            ) : (
              <Bot className="w-4 h-4 text-indigo-400" />
            )}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white truncate">{card.agent}</p>
            <p className="text-[11px] text-neutral-500 capitalize">{card.status?.replace(/_/g, ' ')}</p>
          </div>
        </div>
        <ElapsedTimer running={running} startedAt={card.startedAt} />
      </div>

      <div className="flex flex-wrap gap-1.5">
        <GroundingBadge grounding={card.grounding} />
        {card.policy?.effect && (
          <span className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-neutral-800 text-neutral-300 border-neutral-600">
            policy: {card.policy.effect}
          </span>
        )}
      </div>

      {card.summary && (
        <p className="text-xs text-neutral-400 leading-relaxed">{card.summary}</p>
      )}

      {noData && !running && (
        <p className="text-[11px] text-amber-300/90">
          No live connector data.{' '}
          <a href="/tools" className="underline hover:text-amber-200">Open Tool Registry</a>
        </p>
      )}

      {evidence.length > 0 && (
        <div className="rounded-lg border border-neutral-800 overflow-hidden">
          <button
            type="button"
            onClick={() => setShowEvidence((v) => !v)}
            className="w-full px-3 py-1.5 text-left text-[11px] font-semibold text-neutral-300 bg-neutral-950 hover:bg-neutral-900"
          >
            Evidence ({evidence.length}) {showEvidence ? '▾' : '▸'}
          </button>
          {showEvidence && (
            <ul className="px-3 py-2 space-y-1.5 max-h-40 overflow-y-auto">
              {evidence.map((ev, i) => (
                <li key={i} className="text-[11px] text-neutral-400">
                  <span className="text-neutral-200 font-medium">{ev.title || ev.type}</span>
                  {ev.source ? <span className="text-neutral-500"> · {ev.source}</span> : null}
                  {ev.url ? (
                    <a href={ev.url} target="_blank" rel="noreferrer" className="ml-1 text-indigo-400 underline">link</a>
                  ) : null}
                  {ev.snippet ? <p className="text-neutral-500 truncate">{ev.snippet}</p> : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {card.status === 'failed' && card.summary && (
        <p className="text-[11px] text-red-300/90 border border-red-500/20 bg-red-500/10 rounded-lg px-2 py-1.5">
          {card.summary}
        </p>
      )}

      {pending && (
        <AgentApproveRejectButtons
          busy={busy}
          onApprove={() => onApprove(card)}
          onReject={() => onReject(card)}
        />
      )}
    </div>
  )
}

export default function AgentRunnerPanel() {
  const location = useLocation()
  const { authFetch, token } = useAuth()
  const { toDict, isProduction, workspace_id: workspaceId } = usePlatformContext()
  const { toast } = useToast()

  const [activeTab, setActiveTab] = useState('run')
  const [task, setTask] = useState('')
  const [selectedAgents, setSelectedAgents] = useState([])
  const [cards, setCards] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const actionBusyRef = useRef(false)
  const wsRef = useRef(null)

  useEffect(() => {
    if (
      location.state?.focusHistory ||
      location.state?.goldenPathRun ||
      location.pathname === '/agent-history'
    ) {
      setActiveTab('history')
    }
  }, [location.state, location.pathname])

  const envLabel = isProduction() ? '🔴 PRODUCTION' : '🟡 STAGING'

  const allTerminal = cards.length > 0 && cards.every((c) => TERMINAL_STATUSES.has(c.status))
  const missingWorkspace = !workspaceId
  const canRun =
    !!task.trim() &&
    !missingWorkspace &&
    !submitting &&
    !(cards.length > 0 && !allTerminal)

  const toggleAgent = (name) => {
    setSelectedAgents((prev) =>
      prev.includes(name) ? prev.filter((a) => a !== name) : [...prev, name]
    )
  }

  const closeWs = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  useEffect(() => () => closeWs(), [closeWs])

  const updateCard = useCallback((agent, patch) => {
    setCards((prev) =>
      prev.map((c) => (c.agent === agent ? { ...c, ...patch } : c))
    )
  }, [])

  const connectWs = useCallback(
    (runId, agentNames) => {
      closeWs()
      if (!runId || !token) return

      const ws = new WebSocket(buildAgentRunWsUrl(runId, token))
      wsRef.current = ws

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'error') {
            toast.error(msg.message || 'WebSocket error')
            return
          }
          if (msg.type === 'status' && msg.agent) {
            if (agentNames.length <= 1 || msg.agent !== 'orchestrator') {
              updateCard(msg.agent, {
                status: msg.status,
                summary: msg.summary,
                run_id: msg.run_id || runId,
              })
            } else {
              setCards((prev) =>
                prev.map((c) =>
                  c.status === 'running'
                    ? { ...c, status: msg.status, summary: msg.summary }
                    : c
                )
              )
            }
          }
        } catch {
          /* ignore */
        }
      }

      ws.onerror = () => {
        toast.error('Agent run connection failed')
        setCards((prev) =>
          prev.map((c) =>
            c.status === 'running'
              ? { ...c, status: 'failed', summary: c.summary || 'Connection lost' }
              : c
          )
        )
      }
    },
    [closeWs, token, toast, updateCard]
  )

  const handleRun = async () => {
    const trimmed = task.trim()
    if (!trimmed) {
      toast.warning('Enter a task description')
      return
    }
    if (!workspaceId) {
      toast.warning('Select a workspace before running agents')
      return
    }

    setSubmitting(true)
    closeWs()

    const agentsToRun = selectedAgents.length ? selectedAgents : null
    const initialCards = (agentsToRun || ['agent']).map((name) => ({
      agent: name === 'agent' ? '…' : name,
      run_id: null,
      status: 'running',
      summary: 'Starting…',
      grounding: 'none',
      startedAt: Date.now(),
    }))
    setCards(initialCards)

    try {
      const body = {
        task: trimmed,
        context: toDict(),
        override_agents: agentsToRun,
      }

      const res = await authFetch('/api/agents/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        silentToast: true,
      })

      if (!res.ok) {
        throw new Error(await parseApiError(res, 'Agent run failed'))
      }

      const result = await res.json()
      const parsed = parseMultiAgentCards(result, agentsToRun || [])
      setCards(parsed.map((c) => ({ ...c, startedAt: Date.now() })))

      if (result.status === 'success') {
        toast.success('Agent run completed successfully')
      } else if (result.status === 'pending_approval') {
        toast.warning('Agent run requires approval')
      } else if (result.status === 'failed' || result.status === 'skipped') {
        toast.error(result.summary || 'Agent run failed')
      }

      if (result.run_id) {
        connectWs(
          result.run_id,
          parsed.map((c) => c.agent)
        )
      }
    } catch (e) {
      const msg = e.message || 'Agent run failed'
      toast.error(msg === 'undefined' ? 'Agent run failed' : msg)
      setCards((prev) =>
        prev.map((c) => ({
          ...c,
          status: 'failed',
          summary: msg === 'undefined' ? 'Run failed' : msg,
          grounding: c.grounding || 'none',
        }))
      )
    } finally {
      setSubmitting(false)
    }
  }

  const handleApprove = async (card) => {
    if (!card.run_id || actionBusyRef.current) return
    actionBusyRef.current = true
    setActionBusy(true)
    try {
      const res = await authFetch(`/api/agents/${card.run_id}/approve`, { method: 'POST' })
      if (!res.ok) throw new Error(await parseApiError(res, 'Approve failed'))
      const data = await res.json()
      updateCard(card.agent, {
        status: data.status,
        summary: data.summary,
        grounding: data.grounding ?? card.grounding,
        evidence: data.evidence ?? card.evidence,
        policy: data.policy ?? card.policy,
      })
      toast.success('Agent run approved')
    } catch (e) {
      toast.error(e.message === 'undefined' ? 'Approve failed' : (e.message || 'Approve failed'))
    } finally {
      actionBusyRef.current = false
      setActionBusy(false)
    }
  }

  const handleReject = async (card) => {
    if (!card.run_id || actionBusyRef.current) return
    actionBusyRef.current = true
    setActionBusy(true)
    try {
      const res = await authFetch(`/api/agents/${card.run_id}/reject`, { method: 'POST' })
      if (!res.ok) throw new Error(await parseApiError(res, 'Reject failed'))
      const data = await res.json()
      updateCard(card.agent, { status: data.status || 'rejected', summary: data.summary })
      toast.success('Agent run rejected')
    } catch (e) {
      toast.error(e.message === 'undefined' ? 'Reject failed' : (e.message || 'Reject failed'))
    } finally {
      actionBusyRef.current = false
      setActionBusy(false)
    }
  }

  const handleReset = () => {
    closeWs()
    setCards([])
    setTask('')
    setSelectedAgents([])
  }

  return (
    <div className="p-6 max-w-5xl mx-auto flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Bot className="w-7 h-7 text-indigo-400" />
          Agent Runner
        </h1>
        <p className="text-sm text-neutral-500">
          Dispatch specialist agents against your workspace context.
        </p>
      </div>

      <div className="flex gap-1 border-b border-neutral-800">
        {['run', 'history'].map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px ${
              activeTab === tab
                ? 'border-indigo-500 text-white'
                : 'border-transparent text-neutral-500 hover:text-neutral-300'
            }`}
          >
            {tab === 'run' ? 'Run' : 'History'}
          </button>
        ))}
      </div>

      {activeTab === 'history' ? (
        <AgentRunHistory />
      ) : (
        <div className="flex flex-col gap-5">
          <div className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-5 flex flex-col gap-4">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <label htmlFor="agent-task" className="text-sm font-semibold text-neutral-200">
                Task
              </label>
              <span className="text-xs font-bold px-2.5 py-1 rounded-md border border-neutral-700 bg-neutral-950 text-neutral-300">
                {envLabel}
              </span>
            </div>

            <textarea
              id="agent-task"
              rows={3}
              value={task}
              onChange={(e) => setTask(e.target.value)}
              disabled={submitting || (cards.length > 0 && !allTerminal)}
              placeholder="Describe what you want the agents to do…"
              className="w-full rounded-lg bg-neutral-950 border border-neutral-700 text-sm text-white placeholder:text-neutral-600 px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50 disabled:opacity-60"
            />

            <div>
              <p className="text-xs font-semibold text-neutral-400 mb-2">
                Agents{' '}
                <span className="text-neutral-600 font-normal">
                  (optional — leave empty for auto-routing)
                </span>
              </p>
              <div className="flex flex-wrap gap-2">
                {AGENT_NAMES.map((name) => {
                  const selected = selectedAgents.includes(name)
                  return (
                    <button
                      key={name}
                      type="button"
                      disabled={submitting || (cards.length > 0 && !allTerminal)}
                      onClick={() => toggleAgent(name)}
                      className={`px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors disabled:opacity-50 ${
                        selected
                          ? 'bg-indigo-600/30 border-indigo-500/50 text-indigo-200'
                          : 'bg-neutral-950 border-neutral-700 text-neutral-400 hover:border-neutral-500 hover:text-neutral-200'
                      }`}
                    >
                      {name.replace(/_agent$/, '').replace(/_/g, ' ')}
                    </button>
                  )
                })}
              </div>
            </div>

            {missingWorkspace && (
              <p className="text-[11px] text-amber-300/90">
                Select a workspace in the header before running agents.
              </p>
            )}

            <div className="flex items-center gap-3 pt-1">
              <button
                type="button"
                disabled={!canRun}
                onClick={() => void handleRun()}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold disabled:opacity-50 transition-colors"
              >
                {submitting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Play className="w-4 h-4" />
                )}
                Run Agent
              </button>

              {cards.length > 0 && (
                <button
                  type="button"
                  onClick={handleReset}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-neutral-700 text-neutral-300 text-sm font-medium hover:bg-neutral-800 transition-colors"
                >
                  <RotateCcw className="w-4 h-4" />
                  Reset
                </button>
              )}
            </div>
          </div>

          {cards.length > 0 && (
            <div className="grid gap-3 sm:grid-cols-2">
              {cards.map((card) => (
                <AgentRunCard
                  key={card.agent}
                  card={card}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  busy={actionBusy}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
