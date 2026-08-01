import { useCallback, useEffect, useState } from 'react'
import { ShieldCheck, AlertTriangle, Play, Loader2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { parseApiError } from '../utils/parseApiError'

const EFFECT_STYLES = {
  allow: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  deny: 'bg-red-500/10 text-red-400 border-red-500/30',
  require_approval: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
}

function EffectBadge({ effect }) {
  const cls = EFFECT_STYLES[effect] || 'bg-slate-500/10 text-slate-400 border-slate-500/30'
  return (
    <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${cls}`}>
      {effect}
    </span>
  )
}

export default function CommandPolicyPanel() {
  const { authFetch, role } = useAuth()
  const [rules, setRules] = useState([])
  const [error, setError] = useState(null)
  const [testCmd, setTestCmd] = useState('')
  const [testEnv, setTestEnv] = useState('production')
  const [testing, setTesting] = useState(false)
  const [decision, setDecision] = useState(null)

  const load = useCallback(async () => {
    try {
      const res = await authFetch('/api/policies/commands')
      if (!res.ok) throw new Error('Failed to load command policy rules')
      setRules(await res.json())
    } catch (e) {
      setError(e.message || 'Failed to load command policy rules')
    }
  }, [authFetch])

  useEffect(() => {
    void load()
  }, [load])

  async function runTest(e) {
    e?.preventDefault()
    if (!testCmd.trim()) return
    setTesting(true)
    setDecision(null)
    setError(null)
    try {
      const res = await authFetch('/api/policies/commands/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: testCmd, environment: testEnv, tool: 'shell' }),
      })
      if (!res.ok) throw new Error(await parseApiError(res, 'Evaluation failed'))
      setDecision(await res.json())
    } catch (e2) {
      setError(e2.message || 'Evaluation failed')
    } finally {
      setTesting(false)
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <ShieldCheck className="w-4 h-4 text-emerald-400" />
        <h3 className="text-xs font-bold text-white uppercase tracking-wide">Command policy</h3>
      </div>

      <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-[11px] text-amber-300">
        <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
        Production defaults require human approval for every mutating command. Deny rules
        cannot be bypassed by approval.
      </div>

      {error && (
        <div className="px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-400">
          {error}
        </div>
      )}

      {/* Rules table */}
      <div className="border border-border rounded-lg overflow-hidden">
        <table className="w-full text-[11px]">
          <thead className="bg-sidebar text-slate-400">
            <tr>
              <th className="text-left px-3 py-1.5 font-medium">Rule</th>
              <th className="text-left px-3 py-1.5 font-medium">Effect</th>
              <th className="text-left px-3 py-1.5 font-medium">Environments</th>
              <th className="text-right px-3 py-1.5 font-medium">Priority</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.id} className={`border-t border-border ${r.enabled ? '' : 'opacity-40'}`}>
                <td className="px-3 py-1.5 text-slate-200" title={r.description}>{r.name}</td>
                <td className="px-3 py-1.5"><EffectBadge effect={r.effect} /></td>
                <td className="px-3 py-1.5 text-slate-400">{(r.match_environments || []).join(', ')}</td>
                <td className="px-3 py-1.5 text-right text-slate-400">{r.priority}</td>
              </tr>
            ))}
            {rules.length === 0 && !error && (
              <tr>
                <td colSpan={4} className="px-3 py-3 text-center text-slate-500">No rules loaded</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {role !== 'Admin' && (
        <p className="text-[10px] text-slate-500">Rules are read-only for non-admin users.</p>
      )}

      {/* Test command */}
      <form onSubmit={runTest} className="flex flex-col gap-2">
        <label className="text-[11px] font-medium text-slate-300">Test command</label>
        <div className="flex gap-2">
          <input
            value={testCmd}
            onChange={(e) => setTestCmd(e.target.value)}
            placeholder="kubectl delete pod api-7d9f"
            className="flex-1 px-3 py-1.5 rounded-lg bg-card border border-border text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-accent"
          />
          <select
            value={testEnv}
            onChange={(e) => setTestEnv(e.target.value)}
            className="px-2 py-1.5 rounded-lg bg-card border border-border text-xs text-slate-300"
          >
            <option value="production">production</option>
            <option value="staging">staging</option>
            <option value="development">development</option>
          </select>
          <button
            type="submit"
            disabled={testing || !testCmd.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent/20 border border-accent/40 text-xs text-accent hover:bg-accent/30 disabled:opacity-40"
          >
            {testing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
            Evaluate
          </button>
        </div>
        {decision && (
          <div className="flex flex-col gap-1 px-3 py-2 rounded-lg bg-card border border-border">
            <div className="flex items-center gap-2">
              <EffectBadge effect={decision.effect} />
              <span className="text-[10px] text-slate-500">
                {decision.safe_for_auto ? 'safe for auto-execution' : 'blocked from auto-execution'}
              </span>
            </div>
            {(decision.reasons || []).map((reason, i) => (
              <p key={i} className="text-[10px] text-slate-400">{reason}</p>
            ))}
          </div>
        )}
      </form>
    </section>
  )
}
