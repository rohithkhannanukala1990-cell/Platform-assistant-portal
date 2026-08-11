import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, ChevronDown, ChevronUp, Circle } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { Card } from '../ui'

const LABELS = {
  github: 'GitHub',
  pagerduty: 'PagerDuty',
  kubernetes: 'Kubernetes',
  aws: 'AWS',
  slack: 'Slack',
  datadog: 'Datadog',
  jira: 'Jira',
  gitlab: 'GitLab',
  prometheus: 'Prometheus',
  grafana: 'Grafana',
  vault: 'Vault',
  argocd: 'Argo CD',
}

const DISMISS_KEY = 'dashboard_checklist_dismissed'

export default function SetupChecklistCard() {
  const { authFetch } = useAuth()
  const [items, setItems] = useState(null)
  const [dismissed, setDismissed] = useState(true)
  const [collapsed, setCollapsed] = useState(false)

  const load = useCallback(async () => {
    try {
      const res = await authFetch('/api/tools/connection-summary')
      if (!res.ok) return
      setItems(await res.json())
    } catch {
      setItems(null)
    }
  }, [authFetch])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    authFetch(`/api/user-prefs/${DISMISS_KEY}`)
      .then((r) => (r.ok ? r.json() : { value: null }))
      .then((body) => setDismissed(body.value === '1'))
      .catch(() => setDismissed(true))
  }, [authFetch])

  function dismiss() {
    setDismissed(true)
    void authFetch(`/api/user-prefs/${DISMISS_KEY}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value: '1' }),
    })
  }

  if (dismissed || !items) return null

  const connectedCount = items.filter((i) => i.connected).length

  return (
    <Card className="border-indigo-500/30">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-white">Setup checklist</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {connectedCount} of {items.length} connected — GitHub and PagerDuty matter most, most
            agents depend on them.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            className="text-slate-400 hover:text-white"
          >
            {collapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          </button>
          <button type="button" onClick={dismiss} className="text-xs text-slate-400 hover:text-white">
            Dismiss
          </button>
        </div>
      </div>
      {!collapsed ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 mt-3">
          {items.map((item) => (
            <a
              key={item.id}
              href="/tool-registry"
              className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs ${
                item.connected
                  ? 'border-emerald-500/30 bg-emerald-500/5 text-emerald-200'
                  : 'border-border text-slate-400 hover:bg-slate-800'
              }`}
            >
              {item.connected ? (
                <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
              ) : (
                <Circle className="w-3.5 h-3.5 shrink-0" />
              )}
              <span className="truncate">{LABELS[item.id] || item.id}</span>
            </a>
          ))}
        </div>
      ) : null}
    </Card>
  )
}
