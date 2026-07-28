import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, Loader2, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function OncallWidget({ compact = false, service = null, scheduleId = null }) {
  const { authFetch } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notConnected, setNotConnected] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setNotConnected(false)
    try {
      const params = new URLSearchParams()
      if (service) params.set('service', service)
      if (scheduleId) params.set('schedule_id', scheduleId)
      const qs = params.toString()
      const res = await authFetch(`/api/oncall/now${qs ? `?${qs}` : ''}`)
      if (res.status === 400) {
        setNotConnected(true)
        setData(null)
        return
      }
      if (!res.ok) throw new Error('Failed to load on-call')
      setData(await res.json())
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [authFetch, service, scheduleId])

  useEffect(() => {
    void load()
  }, [load])

  const oncalls = Array.isArray(data?.oncalls) ? data.oncalls : []
  const pdUrl = data?.pd_url || 'https://app.pagerduty.com/schedules'

  if (loading) {
    return (
      <div className={`flex items-center gap-2 text-xs text-slate-500 ${compact ? '' : 'p-4'}`}>
        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading on-call…
      </div>
    )
  }

  if (notConnected) {
    return (
      <div className={`rounded-xl border border-dashed border-border bg-card/40 ${compact ? 'p-3' : 'p-4'}`}>
        <p className="text-xs text-slate-400">PagerDuty not connected.</p>
        <Link to="/tool-registry" className="text-[11px] text-accent hover:underline mt-1 inline-block">
          Connect in Tool Registry
        </Link>
      </div>
    )
  }

  return (
    <div className={`rounded-xl border border-border bg-card/50 ${compact ? 'p-3' : 'p-4'}`}>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-accent" />
          <h3 className="text-sm font-semibold text-white">Who is on-call</h3>
        </div>
        <a
          href={pdUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[10px] text-accent hover:underline"
        >
          Open in PagerDuty
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>
      <p className="text-[10px] text-slate-500 mb-2">
        Scheduling remains in PagerDuty — this widget is read-only.
      </p>
      {!oncalls.length ? (
        <p className="text-xs text-slate-500">No on-call entries for current filters.</p>
      ) : (
        <ul className={`space-y-2 ${compact ? 'text-xs' : 'text-sm'}`}>
          {oncalls.slice(0, compact ? 3 : 8).map((row, idx) => (
            <li key={`${row.user}-${row.schedule}-${idx}`} className="flex flex-wrap gap-x-2 text-slate-300">
              <span className="font-medium text-white">{row.user || '—'}</span>
              <span className="text-slate-500">·</span>
              <span className="text-slate-400">{row.schedule || row.service || 'schedule'}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
