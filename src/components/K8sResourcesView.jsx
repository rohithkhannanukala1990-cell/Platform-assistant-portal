import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Box, Loader2, RefreshCw, Server, Wrench } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

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
        Connect Kubernetes in Tool Registry
      </Link>
    </div>
  )
}

export default function K8sResourcesView() {
  const { authFetch } = useAuth()
  const [tab, setTab] = useState('pods')
  const [namespace, setNamespace] = useState('default')
  const [namespaces, setNamespaces] = useState([])
  const [pods, setPods] = useState([])
  const [nodes, setNodes] = useState([])
  const [loading, setLoading] = useState(true)
  const [notConnected, setNotConnected] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setNotConnected(false)
    try {
      const nsRes = await authFetch('/api/k8s/namespaces')
      if (nsRes.status === 400) {
        setNotConnected(true)
        setNamespaces([])
        setPods([])
        setNodes([])
        return
      }
      if (!nsRes.ok) throw new Error(await nsRes.text())
      const nsList = await nsRes.json()
      setNamespaces(Array.isArray(nsList) ? nsList : [])

      const [podsRes, nodesRes] = await Promise.all([
        authFetch(`/api/k8s/pods?namespace=${encodeURIComponent(namespace)}`),
        authFetch('/api/k8s/nodes'),
      ])
      if (podsRes.status === 400 || nodesRes.status === 400) {
        setNotConnected(true)
        return
      }
      if (!podsRes.ok) throw new Error(await podsRes.text())
      if (!nodesRes.ok) throw new Error(await nodesRes.text())
      setPods(await podsRes.json())
      setNodes(await nodesRes.json())
    } catch (e) {
      setError(e.message || 'Failed to load cluster resources')
    } finally {
      setLoading(false)
    }
  }, [authFetch, namespace])

  useEffect(() => {
    void load()
  }, [load])

  if (loading && !pods.length && !nodes.length && !notConnected) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500 gap-2 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading cluster…
      </div>
    )
  }

  if (notConnected) {
    return (
      <div className="p-4 md:p-6 max-w-5xl mx-auto">
        <h1 className="text-lg font-semibold text-white mb-4">Kubernetes</h1>
        <EmptyConnected
          title="Kubernetes not connected"
          subtitle="Add a kubeconfig or service-account credential in Tool Registry to list pods and nodes."
        />
      </div>
    )
  }

  const rows = tab === 'pods' ? pods : nodes

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6 max-w-5xl mx-auto w-full">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <Server className="w-5 h-5 text-accent" /> Kubernetes
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">Read-only cluster inventory</p>
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

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setTab('pods')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold border ${
            tab === 'pods'
              ? 'border-accent/40 bg-accent/10 text-accent'
              : 'border-border text-slate-400'
          }`}
        >
          <Box className="w-3 h-3 inline mr-1" />
          Pods
        </button>
        <button
          type="button"
          onClick={() => setTab('nodes')}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold border ${
            tab === 'nodes'
              ? 'border-accent/40 bg-accent/10 text-accent'
              : 'border-border text-slate-400'
          }`}
        >
          Nodes
        </button>
        {tab === 'pods' && (
          <select
            value={namespace}
            onChange={(e) => setNamespace(e.target.value)}
            className="ml-auto px-2 py-1.5 rounded-lg bg-surface border border-border text-xs text-slate-300"
          >
            {(namespaces.length ? namespaces : [{ name: 'default' }]).map((ns) => (
              <option key={ns.name || ns} value={ns.name || ns}>
                {ns.name || ns}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="rounded-xl border border-border overflow-hidden">
        <table className="w-full text-left text-xs">
          <thead className="bg-card text-slate-500 uppercase tracking-wider">
            <tr>
              <th className="px-3 py-2 font-semibold">Name</th>
              <th className="px-3 py-2 font-semibold">Status</th>
              {tab === 'pods' ? (
                <>
                  <th className="px-3 py-2 font-semibold">Restarts</th>
                  <th className="px-3 py-2 font-semibold">Node</th>
                </>
              ) : (
                <>
                  <th className="px-3 py-2 font-semibold">Roles</th>
                  <th className="px-3 py-2 font-semibold">CPU</th>
                </>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {!rows.length ? (
              <tr>
                <td colSpan={4} className="px-3 py-8 text-center text-slate-500">
                  No {tab} found.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.name} className="hover:bg-card/50">
                  <td className="px-3 py-2 font-mono text-slate-200">{row.name}</td>
                  <td className="px-3 py-2 text-slate-300">{row.status}</td>
                  {tab === 'pods' ? (
                    <>
                      <td className="px-3 py-2 text-slate-400">{row.restarts ?? 0}</td>
                      <td className="px-3 py-2 text-slate-400">{row.node || '—'}</td>
                    </>
                  ) : (
                    <>
                      <td className="px-3 py-2 text-slate-400">
                        {(row.roles || []).join(', ') || '—'}
                      </td>
                      <td className="px-3 py-2 text-slate-400">{row.cpu || '—'}</td>
                    </>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
