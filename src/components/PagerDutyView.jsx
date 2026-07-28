import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell, Loader2, RefreshCw, Users, Wrench } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import OncallWidget from './OncallWidget'

function EmptyConnected({ title, subtitle }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center border border-dashed border-border rounded-xl bg-card/40">
      <Wrench className="w-8 h-8 text-slate-500 mb-3" />
      <p className="text-sm font-semibold text-slate-200">{title}</p>
      <p className="text-xs text-slate-500 mt-1 max-w-sm">{subtitle}</p>
      <Link
        to="/tool-registry"
        className="mt-4 px-3 py-1.5 text-xs font-semibold rounded-lg bg-accent/15 border border-accent/40 text-accent hover:bg-accent/25"
      >
        Connect PagerDuty in Tool Registry
      </Link>
    </div>
  )
}

export default function PagerDutyView() {
  const { authFetch } = useAuth()
  const [tab, setTab] = useState('incidents')
  const [incidents, setIncidents] = useState([])
  const [oncalls, setOncalls] = useState([])
  const [loading, setLoading] = useState(true)
  const [notConnected, setNotConnected] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setNotConnected(false)
    try {
      const [incRes, ocRes] = await Promise.all([
        authFetch('/api/pagerduty/incidents?limit=30'),
        authFetch('/api/pagerduty/oncalls?limit=30'),
      ])
      if (incRes.status === 400 || ocRes.status === 400) {
        setNotConnected(true)
        setIncidents([])
        setOncalls([])
        return
      }
      if (!incRes.ok) throw new Error(await incRes.text())
      if (!ocRes.ok) throw new Error(await ocRes.text())
      setIncidents(await incRes.json())
      setOncalls(await ocRes.json())
    } catch (e) {
      setError(e.message || 'Failed to load PagerDuty data')
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    void load()
  }, [load])

  if (loading && !incidents.length && !oncalls.length && !notConnected) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500 gap-2 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading PagerDuty…
      </div>
    )
  }

  if (notConnected) {
    return (
      <div className="p-4 md:p-6 max-w-5xl mx-auto">
        <h1 className="text-lg font-semibold text-white mb-4">PagerDuty</h1>
        <EmptyConnected
          title="PagerDuty not connected"
          subtitle="Add an API key in Tool Registry to list incidents and on-call schedules."
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6 max-w-5xl mx-auto w-full">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <Bell className="w-5 h-5 text-accent" /> PagerDuty
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">Incidents and on-call roster</p>
        </div>
        <button
          type="button"
          onClick={() => load()}
          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border text-xs text-slate-400 hover:text-white"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <OncallWidget compact />

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setTab('incidents')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold border ${
            tab === 'incidents'
              ? 'border-accent/40 bg-accent/10 text-accent'
              : 'border-border text-slate-400'
          }`}
        >
          Incidents ({incidents.length})
        </button>
        <button
          type="button"
          onClick={() => setTab('oncalls')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold border ${
            tab === 'oncalls'
              ? 'border-accent/40 bg-accent/10 text-accent'
              : 'border-border text-slate-400'
          }`}
        >
          <Users className="w-3 h-3 inline mr-1" />
          On-call ({oncalls.length})
        </button>
      </div>

      <div className="rounded-xl border border-border overflow-hidden">
        {tab === 'incidents' ? (
          <table className="w-full text-left text-xs">
            <thead className="bg-card text-slate-500 uppercase tracking-wider">
              <tr>
                <th className="px-3 py-2 font-semibold">Title</th>
                <th className="px-3 py-2 font-semibold">Service</th>
                <th className="px-3 py-2 font-semibold">Urgency</th>
                <th className="px-3 py-2 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {!incidents.length ? (
                <tr>
                  <td colSpan={4} className="px-3 py-8 text-center text-slate-500">
                    No open incidents.
                  </td>
                </tr>
              ) : (
                incidents.map((inc) => (
                  <tr key={inc.id} className="hover:bg-card/50">
                    <td className="px-3 py-2 text-slate-200">{inc.title}</td>
                    <td className="px-3 py-2 text-slate-400">{inc.service || '—'}</td>
                    <td className="px-3 py-2 text-slate-400">{inc.urgency || '—'}</td>
                    <td className="px-3 py-2 text-slate-400">{inc.status || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="bg-card text-slate-500 uppercase tracking-wider">
              <tr>
                <th className="px-3 py-2 font-semibold">User</th>
                <th className="px-3 py-2 font-semibold">Schedule</th>
                <th className="px-3 py-2 font-semibold">Policy</th>
                <th className="px-3 py-2 font-semibold">Window</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {!oncalls.length ? (
                <tr>
                  <td colSpan={4} className="px-3 py-8 text-center text-slate-500">
                    No on-call entries.
                  </td>
                </tr>
              ) : (
                oncalls.map((row, i) => (
                  <tr key={i} className="hover:bg-card/50">
                    <td className="px-3 py-2 text-slate-200">{row.user || '—'}</td>
                    <td className="px-3 py-2 text-slate-400">{row.schedule || '—'}</td>
                    <td className="px-3 py-2 text-slate-400">{row.escalation_policy || '—'}</td>
                    <td className="px-3 py-2 text-slate-500 font-mono text-[10px]">
                      {row.start || '—'} → {row.end || '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
