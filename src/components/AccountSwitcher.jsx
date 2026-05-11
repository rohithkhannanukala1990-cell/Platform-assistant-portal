import { useState, useEffect, useRef, useCallback } from 'react'
import { ChevronDown, Star, Plus, AlertTriangle, RefreshCw } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from './ToastNotification'

const GROUP_ORDER = ['PRODUCTION', 'STAGING', 'DR', 'NON-PRODUCTION']

const GROUP_STYLES = {
  PRODUCTION: { label: 'PRODUCTION', headerClass: 'text-red-400 border-red-500/30 bg-red-950/20' },
  STAGING: { label: 'STAGING', headerClass: 'text-amber-300 border-amber-500/30 bg-amber-950/15' },
  DR: { label: 'DR', headerClass: 'text-orange-300 border-orange-500/30 bg-orange-950/15' },
  'NON-PRODUCTION': {
    label: 'NON-PRODUCTION',
    headerClass: 'text-blue-300 border-blue-500/30 bg-blue-950/15',
  },
}

function bucketForAccount(env) {
  const e = (env || '').toLowerCase()
  if (e === 'production') return 'PRODUCTION'
  if (e === 'staging') return 'STAGING'
  if (e === 'dr') return 'DR'
  return 'NON-PRODUCTION'
}

function statusBadge(status) {
  const s = (status || 'unknown').toLowerCase()
  if (s === 'connected')
    return { text: '✅ Connected', className: 'bg-green-500/15 text-green-300 border-green-500/30' }
  if (s === 'failed') return { text: '❌ Failed', className: 'bg-red-500/15 text-red-300 border-red-500/30' }
  if (s === 'unknown') return { text: '⚪ Unknown', className: 'bg-slate-600/40 text-slate-400 border-slate-500/30' }
  return { text: '⚠️ Warning', className: 'bg-amber-500/15 text-amber-200 border-amber-500/30' }
}

function statusDotClass(status) {
  const s = (status || 'unknown').toLowerCase()
  if (s === 'connected') return 'bg-green-500'
  if (s === 'failed') return 'bg-red-500'
  if (s === 'unknown') return 'bg-slate-500'
  return 'bg-amber-400'
}

function formatToolName(toolId, toolNameProp) {
  if (toolNameProp && toolNameProp.trim()) return toolNameProp.trim()
  return toolId
    .split(/[-_]/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ')
}

export default function AccountSwitcher({ toolId, toolName, onAccountChanged }) {
  const { authFetch } = useAuth()
  const { showToast } = useToast()
  const [isOpen, setIsOpen] = useState(false)
  const [accounts, setAccounts] = useState([])
  const [activeAccountId, setActiveAccountId] = useState(null)
  const [pinnedAccountIds, setPinnedAccountIds] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [accessModalOpen, setAccessModalOpen] = useState(false)
  const [accessAccountId, setAccessAccountId] = useState('')
  const [accessReason, setAccessReason] = useState('')
  const [accessError, setAccessError] = useState('')
  const rootRef = useRef(null)

  const displayToolName = formatToolName(toolId || '', toolName)

  const loadData = useCallback(async () => {
    if (!toolId) return
    setIsLoading(true)
    try {
      const [accRes, ctxRes] = await Promise.all([
        authFetch(`/api/tools/${encodeURIComponent(toolId)}/accounts`),
        authFetch('/api/context'),
      ])
      if (accRes.ok) {
        const list = await accRes.json()
        setAccounts(Array.isArray(list) ? list : [])
      } else {
        setAccounts([])
      }
      if (ctxRes.ok) {
        const ctx = await ctxRes.json()
        const map = ctx.active_accounts || {}
        const row = map[toolId]
        setActiveAccountId(row?.id ?? null)
        const pins = ctx.pinned_accounts
        setPinnedAccountIds(Array.isArray(pins) ? pins : [])
      }
    } catch {
      setAccounts([])
    } finally {
      setIsLoading(false)
    }
  }, [authFetch, toolId])

  useEffect(() => {
    void loadData()
  }, [loadData])

  useEffect(() => {
    const onCtx = () => {
      void loadData()
    }
    window.addEventListener('context-changed', onCtx)
    return () => window.removeEventListener('context-changed', onCtx)
  }, [loadData])

  useEffect(() => {
    if (!isOpen) return undefined
    function onDoc(ev) {
      if (rootRef.current && !rootRef.current.contains(ev.target)) setIsOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [isOpen])

  const pinnedForTool = accounts.filter((a) => pinnedAccountIds.includes(a.id))

  const byGroup = {}
  GROUP_ORDER.forEach((g) => {
    byGroup[g] = []
  })
  accounts.forEach((a) => {
    const b = bucketForAccount(a.environment)
    if (!byGroup[b]) byGroup[b] = []
    byGroup[b].push(a)
  })

  const isPinned = (id) => pinnedAccountIds.includes(id)

  async function togglePin(ev, account) {
    ev.stopPropagation()
    const next = !isPinned(account.id)
    try {
      const res = await authFetch('/api/context/pin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: account.id, pinned: next }),
      })
      if (!res.ok) return
      const data = await res.json()
      setPinnedAccountIds(Array.isArray(data.pinned_accounts) ? data.pinned_accounts : [])
      const ctxRes = await authFetch('/api/context')
      const ctx = ctxRes.ok ? await ctxRes.json() : null
      window.dispatchEvent(
        new CustomEvent('context-changed', {
          detail: {
            context: ctx,
            environment: ctx?.active_environment,
            source: 'account-pin',
          },
        })
      )
    } catch {
      /* noop */
    }
  }

  async function selectAccount(account) {
    try {
      const res = await authFetch('/api/context', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_accounts: { [toolId]: account.id } }),
      })
      if (!res.ok) {
        showToast('Could not switch account', 'error')
        return
      }
      const data = await res.json()
      setActiveAccountId(account.id)
      onAccountChanged?.(account)
      window.dispatchEvent(
        new CustomEvent('context-changed', {
          detail: {
            context: data,
            environment: data.active_environment,
            source: 'account-switcher',
          },
        })
      )
      setIsOpen(false)
    } catch {
      showToast('Could not switch account', 'error')
    }
  }

  const activeAccount = accounts.find((a) => a.id === activeAccountId)

  function openAccessModal() {
    setAccessAccountId(accounts[0]?.id || '')
    setAccessReason('')
    setAccessError('')
    setAccessModalOpen(true)
    setIsOpen(false)
  }

  async function submitAccessRequest() {
    const reason = accessReason.trim()
    if (reason.length < 20) {
      setAccessError('Reason must be at least 20 characters.')
      return
    }
    if (!accessAccountId) {
      setAccessError('Select an account.')
      return
    }
    setAccessError('')
    try {
      const res = await authFetch('/api/access-requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: accessAccountId, reason }),
      })
      if (!res.ok) {
        const t = await res.text()
        setAccessError(t || 'Request failed')
        return
      }
      showToast('Access request submitted', 'success')
      setAccessModalOpen(false)
    } catch (e) {
      setAccessError(String(e?.message || e))
    }
  }

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setIsOpen((o) => !o)}
        disabled={!toolId}
        className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-700 bg-gray-800 text-sm text-slate-200 hover:bg-gray-700/80 disabled:opacity-50"
        aria-expanded={isOpen}
      >
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${activeAccount ? statusDotClass(activeAccount.status) : 'bg-slate-600'}`}
        />
        <span className="font-medium truncate max-w-[160px]">
          {activeAccount ? activeAccount.account_name : 'No Account Selected'}
        </span>
        {isLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin text-slate-500 shrink-0" />}
        <ChevronDown className={`w-4 h-4 text-slate-500 shrink-0 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && toolId && (
        <div className="absolute left-0 top-full mt-1 z-50 w-[320px] max-h-[400px] overflow-y-auto rounded-lg border border-gray-700 bg-gray-800 shadow-xl flex flex-col">
          <div className="px-3 py-2 border-b border-gray-700 text-xs font-semibold text-slate-400 uppercase tracking-wide">
            Select {displayToolName} Account
          </div>

          <div className="py-1 flex-1 min-h-0">
            {pinnedForTool.length > 0 && (
              <div className="mb-1">
                <div className="px-3 py-1 text-[10px] font-bold text-amber-300/90 uppercase tracking-wider">
                  ⭐ Pinned
                </div>
                {pinnedForTool.map((account) => (
                  <AccountRow
                    key={`pin-${account.id}`}
                    account={account}
                    activeAccountId={activeAccountId}
                    isPinned={isPinned(account.id)}
                    onPin={togglePin}
                    onSelect={() => void selectAccount(account)}
                  />
                ))}
              </div>
            )}

            {GROUP_ORDER.map((groupKey) => {
              const list = byGroup[groupKey] || []
              if (!list.length) return null
              const meta = GROUP_STYLES[groupKey]
              return (
                <div key={groupKey} className="mb-1">
                  <div
                    className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider border-b ${meta.headerClass}`}
                  >
                    {meta.label}
                  </div>
                  {list.map((account) => (
                    <AccountRow
                      key={account.id}
                      account={account}
                      activeAccountId={activeAccountId}
                      isPinned={isPinned(account.id)}
                      onPin={togglePin}
                      onSelect={() => void selectAccount(account)}
                    />
                  ))}
                </div>
              )
            })}
          </div>

          <div className="border-t border-gray-700 px-3 py-2 flex flex-col gap-1 shrink-0 bg-gray-900/40">
            <button
              type="button"
              onClick={openAccessModal}
              className="text-xs text-accent hover:underline flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" />
              Request Access
            </button>
            <span className="text-[10px] text-slate-500">Showing {accounts.length} accounts</span>
          </div>
        </div>
      )}

      {accessModalOpen && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/70">
          <div className="w-full max-w-md rounded-xl border border-gray-700 bg-gray-800 shadow-2xl p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Request account access</h3>
            <label className="block text-[10px] uppercase text-slate-500 mb-1">Account</label>
            <select
              className="w-full rounded-lg bg-gray-900 border border-gray-600 px-3 py-2 text-sm text-white mb-3"
              value={accessAccountId}
              onChange={(e) => setAccessAccountId(e.target.value)}
              disabled={accounts.length === 0}
            >
              {accounts.length === 0 ? (
                <option value="">No accounts for this tool</option>
              ) : (
                accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.account_name} ({a.environment})
                  </option>
                ))
              )}
            </select>
            <label className="block text-[10px] uppercase text-slate-500 mb-1">Reason (min 20 characters)</label>
            <textarea
              className="w-full rounded-lg bg-gray-900 border border-gray-600 px-3 py-2 text-sm text-white min-h-[88px]"
              placeholder="Describe why you need access..."
              value={accessReason}
              onChange={(e) => setAccessReason(e.target.value)}
            />
            {accessError && (
              <p className="text-xs text-red-400 mt-2 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                {accessError}
              </p>
            )}
            <div className="mt-4 flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => setAccessModalOpen(false)}
                className="px-3 py-1.5 rounded-lg border border-gray-600 text-sm text-slate-300 hover:bg-gray-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void submitAccessRequest()}
                className="px-3 py-1.5 rounded-lg bg-accent text-white text-sm font-medium hover:opacity-90"
              >
                Submit Request
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function AccountRow({ account, activeAccountId, isPinned, onPin, onSelect }) {
  const badge = statusBadge(account.status)
  const active = account.id === activeAccountId
  return (
    <div
      className={`w-full px-3 py-2 flex items-start gap-2 border-b border-gray-700/40 ${
        active ? 'bg-gray-700/30' : ''
      }`}
    >
      <button
        type="button"
        onClick={(e) => onPin(e, account)}
        className="p-0.5 rounded mt-0.5 text-amber-400 hover:bg-gray-600 shrink-0"
        title={isPinned ? 'Unpin' : 'Pin'}
      >
        <Star className={`w-4 h-4 ${isPinned ? 'fill-amber-400 text-amber-400' : 'text-slate-500'}`} />
      </button>
      <button
        type="button"
        onClick={onSelect}
        className="min-w-0 flex-1 text-left hover:opacity-95"
      >
        <div className={`text-sm ${active ? 'font-bold text-white' : 'text-slate-200'}`}>{account.account_name}</div>
        <div className="flex flex-wrap items-center gap-1.5 mt-1">
          {account.region && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 border border-slate-600">
              {account.region}
            </span>
          )}
          <span className={`text-[10px] px-1.5 py-0.5 rounded border capitalize ${badge.className}`}>
            {badge.text}
          </span>
        </div>
      </button>
      <span className="flex flex-col items-center gap-0.5 shrink-0 pt-1 w-4">
        {active && <span className="text-accent text-xs" title="Active">●</span>}
      </span>
    </div>
  )
}
