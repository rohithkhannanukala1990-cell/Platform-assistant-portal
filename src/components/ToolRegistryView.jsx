/**
 * Tool credential registry (admin). Mock data until tool_accounts API exists.
 */
import { useState, useCallback } from 'react'
import { Wrench, Pencil } from 'lucide-react'
import { useRole } from '../contexts/RoleContext'

const MOCK_ACCOUNTS = [
  { id: 'acc-1', account_name: 'prod-github-app', tool: 'GitHub', expiry_days: 45 },
  { id: 'acc-2', account_name: 'snowflake-svc', tool: 'Snowflake', expiry_days: 14 },
  { id: 'acc-3', account_name: 'datadog-api', tool: 'Datadog', expiry_days: 5 },
  { id: 'acc-4', account_name: 'legacy-jenkins', tool: 'Jenkins', expiry_days: 0 },
]

function ExpiryBadge({ days }) {
  if (days == null || days > 30) return null
  if (days <= 0) {
    return (
      <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-red-500/20 text-red-300 border border-red-500/35">
        ❌ Expired
      </span>
    )
  }
  if (days <= 7) {
    return (
      <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-red-500/20 text-red-300 border border-red-500/35">
        🔴 Expires in {days}d
      </span>
    )
  }
  if (days <= 30) {
    return (
      <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-orange-500/15 text-orange-300 border border-orange-500/30">
        ⚠️ Expires in {days}d
      </span>
    )
  }
  return null
}

export default function ToolRegistryView() {
  const { role } = useRole()
  const [accounts] = useState(MOCK_ACCOUNTS)
  const [editId, setEditId] = useState(null)
  const [secretDraft, setSecretDraft] = useState('')
  const [toast, setToast] = useState(null)

  const showToast = useCallback((msg) => {
    setToast(msg)
    window.setTimeout(() => setToast(null), 4000)
  }, [])

  if (role !== 'Admin') {
    return (
      <div className="max-w-md mx-auto mt-16 text-center text-slate-500 text-sm">
        Tool registry is restricted to Admins.
      </div>
    )
  }

  function openRotate(acc) {
    setEditId(acc.id)
    setSecretDraft('')
  }

  function saveRotate() {
    if (!editId) return
    setEditId(null)
    setSecretDraft('')
    showToast('✅ Credentials rotated successfully')
    // In production: PATCH account + re-test connection API
  }

  return (
    <div className="max-w-5xl mx-auto pb-16">
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 px-4 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}

      <header className="mb-8 flex items-center gap-3">
        <Wrench className="w-7 h-7 text-accent" />
        <div>
          <h1 className="text-xl font-bold text-white">Tool Registry</h1>
          <p className="text-sm text-slate-500">Integration accounts and credential rotation</p>
        </div>
      </header>

      <div className="overflow-x-auto rounded-xl border border-border bg-card/40">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="text-slate-500 border-b border-border">
              <th className="p-4 font-medium">Account</th>
              <th className="p-4 font-medium">Tool</th>
              <th className="p-4 font-medium">Expiry</th>
              <th className="p-4 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((acc) => (
              <tr key={acc.id} className="border-b border-border/60 hover:bg-card/50">
                <td className="p-4 text-white font-medium">
                  {acc.account_name}
                  <ExpiryBadge days={acc.expiry_days} />
                </td>
                <td className="p-4 text-slate-300">{acc.tool}</td>
                <td className="p-4 text-slate-400 font-mono text-xs">
                  {acc.expiry_days != null ? `${acc.expiry_days} days` : '—'}
                </td>
                <td className="p-4 text-right whitespace-nowrap">
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs border border-border text-slate-300 hover:text-white mr-2"
                    onClick={() => openRotate(acc)}
                  >
                    <Pencil className="w-3 h-3" />
                    Edit
                  </button>
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs bg-emerald-900/30 border border-emerald-700/40 text-emerald-200 hover:bg-emerald-900/50"
                    onClick={() => openRotate(acc)}
                  >
                    Rotate Credentials
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-2xl">
            <h2 className="text-lg font-semibold text-white mb-2">Update credentials</h2>
            <p className="text-xs text-slate-500 mb-4">
              Paste new API token or secret. On save we re-test the connection (mock).
            </p>
            <textarea
              className="w-full h-24 rounded-lg bg-card border border-border p-3 text-sm text-slate-200 font-mono"
              placeholder="••••••••"
              value={secretDraft}
              onChange={(e) => setSecretDraft(e.target.value)}
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="px-3 py-1.5 rounded-lg text-sm text-slate-400 hover:text-white"
                onClick={() => { setEditId(null); setSecretDraft('') }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="px-3 py-1.5 rounded-lg text-sm bg-accent text-white font-medium"
                onClick={saveRotate}
              >
                Save &amp; re-test
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
