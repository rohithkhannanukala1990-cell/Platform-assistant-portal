import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, RotateCcw, X, Loader2, Share2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usePortalContext } from '../contexts/PortalContext'
import RelatedAgentsBar from './RelatedAgentsBar'

const WIDTH = 800
const HEIGHT = 600
const CENTER_X = WIDTH / 2
const CENTER_Y = HEIGHT / 2
const KIND_FILTERS = ['All', 'Service', 'API', 'Library', 'Website']

const KIND_FILL = {
  Service: '#3b82f6',
  API: '#22c55e',
  Library: '#eab308',
  Website: '#a855f7',
}

const EDGE_STROKE = {
  calls: '#818cf8',
  uses: '#34d399',
  depends_on: '#fbbf24',
}

function randomPosition() {
  return {
    x: 80 + Math.random() * (WIDTH - 160),
    y: 80 + Math.random() * (HEIGHT - 160),
  }
}

function truncateName(name, max = 10) {
  if (!name) return ''
  return name.length > max ? `${name.slice(0, max)}…` : name
}

function runForceSimulation(nodes, edges) {
  const sim = nodes.map((n) => ({ ...n, vx: n.vx ?? 0, vy: n.vy ?? 0 }))

  for (let tick = 0; tick < 60; tick += 1) {
    const forces = sim.map(() => ({ fx: 0, fy: 0 }))

    for (let i = 0; i < sim.length; i += 1) {
      for (let j = i + 1; j < sim.length; j += 1) {
        let dx = sim[j].x - sim[i].x
        let dy = sim[j].y - sim[i].y
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.1
        const f = 5000 / (dist * dist)
        dx /= dist
        dy /= dist
        forces[i].fx -= dx * f
        forces[i].fy -= dy * f
        forces[j].fx += dx * f
        forces[j].fy += dy * f
      }
    }

    for (const edge of edges) {
      const i = sim.findIndex((n) => n.id === edge.from_entity_id)
      const j = sim.findIndex((n) => n.id === edge.to_entity_id)
      if (i < 0 || j < 0) continue
      let dx = sim[j].x - sim[i].x
      let dy = sim[j].y - sim[i].y
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.1
      const f = (dist - 150) * 0.05
      dx /= dist
      dy /= dist
      forces[i].fx += dx * f
      forces[i].fy += dy * f
      forces[j].fx -= dx * f
      forces[j].fy -= dy * f
    }

    for (let i = 0; i < sim.length; i += 1) {
      forces[i].fx += (CENTER_X - sim[i].x) * 0.01
      forces[i].fy += (CENTER_Y - sim[i].y) * 0.01
    }

    for (let i = 0; i < sim.length; i += 1) {
      sim[i].vx = (sim[i].vx + forces[i].fx) * 0.85
      sim[i].vy = (sim[i].vy + forces[i].fy) * 0.85
      sim[i].x = Math.max(40, Math.min(760, sim[i].x + sim[i].vx))
      sim[i].y = Math.max(40, Math.min(560, sim[i].y + sim[i].vy))
    }
  }

  return sim
}

function clientToSvg(svg, clientX, clientY) {
  const pt = svg.createSVGPoint()
  pt.x = clientX
  pt.y = clientY
  const ctm = svg.getScreenCTM()
  if (!ctm) return { x: clientX, y: clientY }
  const svgPt = pt.matrixTransform(ctm.inverse())
  return { x: svgPt.x, y: svgPt.y }
}

export default function DependencyGraph() {
  const { authFetch } = useAuth()
  const { activeWorkspace } = usePortalContext()
  const workspaceId = activeWorkspace?.id ?? ''
  const navigate = useNavigate()
  const svgRef = useRef(null)
  const dragMovedRef = useRef(false)
  const edgesRef = useRef([])

  const [entities, setEntities] = useState([])
  const [nodes, setNodes] = useState([])
  const [edges, setEdges] = useState([])
  const [selected, setSelected] = useState(null)
  const [kindFilter, setKindFilter] = useState('All')
  const [showAddForm, setShowAddForm] = useState(false)
  const [dragging, setDragging] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [simTick, setSimTick] = useState(0)
  const [addForm, setAddForm] = useState({ from_entity_id: '', to_entity_id: '', dep_type: 'calls' })
  const [saving, setSaving] = useState(false)
  const [driftResult, setDriftResult] = useState(null)
  const [driftLoading, setDriftLoading] = useState(false)

  const handleCheckDrift = async () => {
    setDriftLoading(true)
    try {
      const res = await authFetch('/api/agents/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: 'check dependency drift outdated packages',
          workspace_id: workspaceId,
        }),
      })
      const data = await res.json()
      setDriftResult(data)
    } catch {
      setDriftResult({
        status: 'failed',
        summary: 'Drift check failed',
      })
    } finally {
      setDriftLoading(false)
    }
  }

  const loadEdges = useCallback(async () => {
    const res = await authFetch('/api/catalog/dependencies')
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    setEdges(Array.isArray(data) ? data : [])
  }, [authFetch])

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await authFetch('/api/catalog')
      if (!res.ok) throw new Error(await res.text())
      const catalog = await res.json()
      setEntities(Array.isArray(catalog) ? catalog : [])
      const initialNodes = (Array.isArray(catalog) ? catalog : []).map((e) => ({
        id: e.id,
        name: e.name,
        kind: e.kind,
        ...randomPosition(),
        vx: 0,
        vy: 0,
      }))
      setNodes(initialNodes)
      await loadEdges()
      setSimTick((t) => t + 1)
    } catch (e) {
      setError(e.message || 'Failed to load dependency graph')
    } finally {
      setLoading(false)
    }
  }, [authFetch, loadEdges])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  useEffect(() => {
    edgesRef.current = edges
  }, [edges])

  useEffect(() => {
    if (!nodes.length || simTick === 0) return
    setNodes((prev) => runForceSimulation(prev, edgesRef.current))
  }, [simTick, nodes.length])

  const visibleNodeIds = useMemo(() => {
    const set = new Set()
    for (const n of nodes) {
      if (kindFilter === 'All' || n.kind === kindFilter) set.add(n.id)
    }
    return set
  }, [nodes, kindFilter])

  const visibleNodes = useMemo(
    () => nodes.filter((n) => visibleNodeIds.has(n.id)),
    [nodes, visibleNodeIds]
  )

  const visibleEdges = useMemo(
    () =>
      edges.filter(
        (e) => visibleNodeIds.has(e.from_entity_id) && visibleNodeIds.has(e.to_entity_id)
      ),
    [edges, visibleNodeIds]
  )

  const nodeById = useMemo(() => {
    const map = {}
    for (const n of nodes) map[n.id] = n
    return map
  }, [nodes])

  const selectedEntity = useMemo(
    () => entities.find((e) => e.id === selected) ?? null,
    [entities, selected]
  )

  const selectedEdges = useMemo(() => {
    if (!selected) return []
    return edges.filter((e) => e.from_entity_id === selected || e.to_entity_id === selected)
  }, [edges, selected])

  const resetLayout = () => {
    setNodes((prev) =>
      prev.map((n) => ({
        ...n,
        ...randomPosition(),
        vx: 0,
        vy: 0,
      }))
    )
    setSimTick((t) => t + 1)
  }

  const removeEdge = async (depId) => {
    try {
      const res = await authFetch(`/api/catalog/dependencies/${encodeURIComponent(depId)}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error(await res.text())
      await loadEdges()
    } catch (e) {
      setError(e.message || 'Failed to remove dependency')
    }
  }

  const saveDependency = async (ev) => {
    ev.preventDefault()
    if (!addForm.from_entity_id || !addForm.to_entity_id) return
    setSaving(true)
    try {
      const res = await authFetch('/api/catalog/dependencies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(addForm),
      })
      if (!res.ok) throw new Error(await res.text())
      setShowAddForm(false)
      setAddForm({ from_entity_id: '', to_entity_id: '', dep_type: 'calls' })
      await loadEdges()
      setSimTick((t) => t + 1)
    } catch (e) {
      setError(e.message || 'Failed to create dependency')
    } finally {
      setSaving(false)
    }
  }

  const onSvgMouseMove = (ev) => {
    if (!dragging || !svgRef.current) return
    dragMovedRef.current = true
    const { x, y } = clientToSvg(svgRef.current, ev.clientX, ev.clientY)
    setNodes((prev) =>
      prev.map((n) =>
        n.id === dragging.nodeId
          ? {
              ...n,
              x: Math.max(40, Math.min(760, x - dragging.offsetX)),
              y: Math.max(40, Math.min(560, y - dragging.offsetY)),
              vx: 0,
              vy: 0,
            }
          : n
      )
    )
  }

  const endDrag = () => {
    if (dragging && !dragMovedRef.current) {
      setSelected(dragging.nodeId)
    }
    setDragging(null)
    dragMovedRef.current = false
  }

  const startDrag = (ev, nodeId) => {
    ev.stopPropagation()
    if (!svgRef.current) return
    dragMovedRef.current = false
    const { x, y } = clientToSvg(svgRef.current, ev.clientX, ev.clientY)
    const node = nodeById[nodeId]
    if (!node) return
    setDragging({
      nodeId,
      offsetX: x - node.x,
      offsetY: y - node.y,
    })
  }

  const viewInCatalog = () => {
    if (!selectedEntity) return
    navigate('/catalog', { state: { catalogSearch: selectedEntity.name } })
  }

  return (
    <div className="flex flex-col gap-4 max-w-5xl mx-auto pb-16 animate-fade-in w-full">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Service Dependency Graph</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Catalog entities and relationships — drag nodes, filter by kind, add dependencies
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/data-lineage')}
          className="shrink-0 text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors"
        >
          <Share2 className="w-3 h-3" />
          Data Lineage
        </button>
      </div>

      <RelatedAgentsBar surface="dependencies" />

      {error && (
        <div className="px-4 py-2 rounded-lg border border-red-800 bg-red-950/40 text-red-200 text-sm">
          {error}
        </div>
      )}

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-gray-800">
          <div className="flex flex-wrap gap-1.5">
            {KIND_FILTERS.map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKindFilter(k)}
                className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-colors ${
                  kindFilter === k
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
              >
                {k}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowAddForm(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"
            >
              <Plus className="w-3.5 h-3.5" /> Add Dependency
            </button>
            <button
              type="button"
              onClick={resetLayout}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-700 text-slate-300 hover:bg-gray-800 text-xs font-semibold"
            >
              <RotateCcw className="w-3.5 h-3.5" /> Reset Layout
            </button>
            <button
              type="button"
              onClick={() => void handleCheckDrift()}
              disabled={driftLoading}
              className="flex items-center gap-2 bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded-lg"
            >
              {driftLoading ? <span className="animate-spin">⟳</span> : '⚡'}
              {driftLoading ? 'Checking…' : 'Check Drift'}
            </button>
          </div>
        </div>

        {driftResult && (
          <div
            className={`mx-4 mb-3 rounded-lg p-3 text-sm border flex items-start gap-3 ${
              driftResult.status === 'success'
                ? 'bg-green-900/20 border-green-700 text-green-300'
                : 'bg-orange-900/20 border-orange-700 text-orange-300'
            }`}
          >
            <span className="mt-0.5">{driftResult.status === 'success' ? '✅' : '⚡'}</span>
            <div>
              <p className="font-medium">{driftResult.summary}</p>
              {driftResult.details?.outdated_count !== undefined && (
                <p className="text-xs mt-0.5 opacity-80">
                  {driftResult.details.outdated_count} outdated packages found
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => setDriftResult(null)}
              className="ml-auto text-xs opacity-50 hover:opacity-100"
            >
              ✕
            </button>
          </div>
        )}

        <div className="relative">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-gray-900/80">
              <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
          )}

          <svg
            ref={svgRef}
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            preserveAspectRatio="xMidYMid meet"
            className="w-full h-auto block bg-gray-950 cursor-default select-none"
            onMouseMove={onSvgMouseMove}
            onMouseUp={endDrag}
            onMouseLeave={endDrag}
          >
            <defs>
              <marker
                id="arrow-calls"
                markerWidth="8"
                markerHeight="8"
                refX="6"
                refY="4"
                orient="auto"
              >
                <path d="M0,0 L8,4 L0,8 Z" fill={EDGE_STROKE.calls} />
              </marker>
              <marker
                id="arrow-uses"
                markerWidth="8"
                markerHeight="8"
                refX="6"
                refY="4"
                orient="auto"
              >
                <path d="M0,0 L8,4 L0,8 Z" fill={EDGE_STROKE.uses} />
              </marker>
              <marker
                id="arrow-depends_on"
                markerWidth="8"
                markerHeight="8"
                refX="6"
                refY="4"
                orient="auto"
              >
                <path d="M0,0 L8,4 L0,8 Z" fill={EDGE_STROKE.depends_on} />
              </marker>
            </defs>

            {visibleEdges.map((edge) => {
              const from = nodeById[edge.from_entity_id]
              const to = nodeById[edge.to_entity_id]
              if (!from || !to) return null
              const stroke = EDGE_STROKE[edge.dep_type] || EDGE_STROKE.calls
              const markerId = `url(#arrow-${edge.dep_type === 'depends_on' ? 'depends_on' : edge.dep_type})`
              const mx = (from.x + to.x) / 2
              const my = (from.y + to.y) / 2
              return (
                <g key={edge.id}>
                  <line
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                    stroke={stroke}
                    strokeWidth={2}
                    markerEnd={markerId}
                  />
                  <text
                    x={mx}
                    y={my - 6}
                    textAnchor="middle"
                    className="fill-gray-400"
                    style={{ fontSize: 10 }}
                  >
                    {edge.dep_type}
                  </text>
                </g>
              )
            })}

            {visibleNodes.map((node) => {
              const fill = KIND_FILL[node.kind] || '#6b7280'
              const isSelected = selected === node.id
              return (
                <g
                  key={node.id}
                  onMouseDown={(ev) => startDrag(ev, node.id)}
                  style={{ cursor: dragging?.nodeId === node.id ? 'grabbing' : 'grab' }}
                >
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={28}
                    fill={fill}
                    stroke={isSelected ? '#ffffff' : 'none'}
                    strokeWidth={isSelected ? 2 : 0}
                  />
                  <text
                    x={node.x}
                    y={node.y}
                    dy={42}
                    textAnchor="middle"
                    className="fill-white pointer-events-none"
                    style={{ fontSize: 11 }}
                  >
                    {truncateName(node.name)}
                  </text>
                </g>
              )
            })}
          </svg>

          {selectedEntity && (
            <div className="absolute top-3 right-3 w-64 rounded-lg border border-gray-700 bg-gray-900/95 shadow-xl p-4 text-sm z-20">
              <p className="font-bold text-white truncate">{selectedEntity.name}</p>
              <dl className="mt-2 space-y-1 text-slate-400 text-xs">
                <div className="flex justify-between gap-2">
                  <dt>Kind</dt>
                  <dd className="text-slate-200">{selectedEntity.kind}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Lifecycle</dt>
                  <dd className="text-slate-200">{selectedEntity.lifecycle}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Owner</dt>
                  <dd className="text-slate-200 truncate">{selectedEntity.owner_team}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Health</dt>
                  <dd className="text-slate-200">{selectedEntity.health_status}</dd>
                </div>
              </dl>
              <button
                type="button"
                onClick={viewInCatalog}
                className="mt-3 w-full py-2 rounded-lg bg-slate-800 border border-gray-700 text-white text-xs font-semibold hover:bg-slate-700"
              >
                View in Catalog
              </button>
              {selectedEdges.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-700">
                  <p className="text-xs font-semibold text-slate-500 uppercase mb-2">Dependencies</p>
                  <ul className="space-y-1.5 max-h-32 overflow-y-auto">
                    {selectedEdges.map((edge) => (
                      <li
                        key={edge.id}
                        className="flex items-start justify-between gap-2 text-xs text-slate-300"
                      >
                        <span className="min-w-0 leading-snug">
                          {edge.from_name} → {edge.to_name}{' '}
                          <span className="text-slate-500">({edge.dep_type})</span>
                        </span>
                        <button
                          type="button"
                          onClick={() => void removeEdge(edge.id)}
                          className="shrink-0 p-0.5 text-slate-500 hover:text-red-400"
                          aria-label="Remove dependency"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {showAddForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70">
          <form
            onSubmit={(ev) => void saveDependency(ev)}
            className="w-full max-w-md rounded-xl border border-gray-700 bg-gray-900 p-6 shadow-2xl space-y-4"
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-white">Add Dependency</h3>
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <label className="block text-xs font-semibold text-slate-400 uppercase">
              From
              <select
                required
                value={addForm.from_entity_id}
                onChange={(ev) => setAddForm({ ...addForm, from_entity_id: ev.target.value })}
                className="mt-1 w-full px-3 py-2 rounded-lg bg-gray-950 border border-gray-700 text-white text-sm"
              >
                <option value="">Select entity…</option>
                {entities.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name} ({e.kind})
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-semibold text-slate-400 uppercase">
              To
              <select
                required
                value={addForm.to_entity_id}
                onChange={(ev) => setAddForm({ ...addForm, to_entity_id: ev.target.value })}
                className="mt-1 w-full px-3 py-2 rounded-lg bg-gray-950 border border-gray-700 text-white text-sm"
              >
                <option value="">Select entity…</option>
                {entities.map((e) => (
                  <option key={`to-${e.id}`} value={e.id}>
                    {e.name} ({e.kind})
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-semibold text-slate-400 uppercase">
              Type
              <select
                value={addForm.dep_type}
                onChange={(ev) => setAddForm({ ...addForm, dep_type: ev.target.value })}
                className="mt-1 w-full px-3 py-2 rounded-lg bg-gray-950 border border-gray-700 text-white text-sm"
              >
                <option value="calls">calls</option>
                <option value="uses">uses</option>
                <option value="depends_on">depends_on</option>
              </select>
            </label>
            <div className="flex gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="flex-1 py-2.5 rounded-lg border border-gray-700 text-slate-300 text-sm font-semibold hover:bg-gray-800"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="flex-1 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold disabled:opacity-50"
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
