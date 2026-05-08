import { useState } from 'react'
import { GitMerge, Database, Cloud, Zap, Box, Info, X } from 'lucide-react'

// ── Graph data ─────────────────────────────────────────────────────────────────
const NODES = [
  // Sources
  { id: 'src-kafka',      label: 'Kafka',           sublabel: 'Event stream',    type: 'source',      x: 0,   y: 1,   icon: '⚡' },
  { id: 'src-postgres',   label: 'PostgreSQL',       sublabel: 'OLTP primary',    type: 'source',      x: 0,   y: 3,   icon: '🐘' },
  { id: 'src-s3',         label: 'S3 Raw Logs',      sublabel: 'Object storage',  type: 'source',      x: 0,   y: 5,   icon: '📦' },
  { id: 'src-snowflake',  label: 'Snowflake CRM',    sublabel: 'SaaS connector',  type: 'source',      x: 0,   y: 7,   icon: '❄️' },

  // Transforms
  { id: 'tf-events',      label: 'Event Enricher',   sublabel: 'Flink job',       type: 'transform',   x: 2.5, y: 1,   icon: '⚙️' },
  { id: 'tf-dbt-core',    label: 'dbt Core',         sublabel: 'SQL transforms',  type: 'transform',   x: 2.5, y: 4,   icon: '🔧' },
  { id: 'tf-ml-prep',     label: 'ML Feature Eng.',  sublabel: 'PySpark job',     type: 'transform',   x: 2.5, y: 6.5, icon: '🤖' },

  // Destinations
  { id: 'dst-bq',         label: 'BigQuery DWH',     sublabel: 'Analytics store', type: 'destination', x: 5,   y: 2,   icon: '🔵' },
  { id: 'dst-redis',      label: 'Redis Cache',       sublabel: 'Feature store',   type: 'destination', x: 5,   y: 5,   icon: '⚡' },
  { id: 'dst-elastic',    label: 'Elasticsearch',     sublabel: 'Log search',      type: 'destination', x: 5,   y: 7,   icon: '🔍' },

  // Consumers
  { id: 'con-dashboard',  label: 'Analytics Dash',   sublabel: 'Looker Studio',   type: 'consumer',    x: 7.5, y: 1,   icon: '📊' },
  { id: 'con-mlmodel',    label: 'ML Models',         sublabel: 'Inference API',   type: 'consumer',    x: 7.5, y: 4,   icon: '🧠' },
  { id: 'con-alerts',     label: 'Alert Engine',      sublabel: 'PagerDuty',       type: 'consumer',    x: 7.5, y: 6.5, icon: '🔔' },
]

const EDGES = [
  { from: 'src-kafka',     to: 'tf-events',    label: 'stream' },
  { from: 'src-postgres',  to: 'tf-dbt-core',  label: 'CDC' },
  { from: 'src-s3',        to: 'tf-dbt-core',  label: 'batch' },
  { from: 'src-snowflake', to: 'tf-dbt-core',  label: 'sync' },
  { from: 'src-s3',        to: 'tf-ml-prep',   label: 'batch' },
  { from: 'src-kafka',     to: 'dst-elastic',  label: 'stream' },
  { from: 'tf-events',     to: 'dst-bq',       label: 'sink' },
  { from: 'tf-events',     to: 'dst-redis',    label: 'cache' },
  { from: 'tf-dbt-core',   to: 'dst-bq',       label: 'load' },
  { from: 'tf-ml-prep',    to: 'dst-redis',    label: 'features' },
  { from: 'dst-bq',        to: 'con-dashboard', label: 'query' },
  { from: 'dst-bq',        to: 'con-mlmodel',  label: 'training' },
  { from: 'dst-redis',     to: 'con-mlmodel',  label: 'inference' },
  { from: 'dst-elastic',   to: 'con-alerts',   label: 'search' },
]

const TYPE_CFG = {
  source:      { bg: 'bg-blue-500/15 border-blue-500/40',       text: 'text-blue-300',   label: 'Source',      dot: 'bg-blue-400'    },
  transform:   { bg: 'bg-amber-500/15 border-amber-500/40',     text: 'text-amber-300',  label: 'Transform',   dot: 'bg-amber-400'   },
  destination: { bg: 'bg-green-500/15 border-green-500/40',     text: 'text-green-300',  label: 'Destination', dot: 'bg-green-400'   },
  consumer:    { bg: 'bg-purple-500/15 border-purple-500/40',   text: 'text-purple-300', label: 'Consumer',    dot: 'bg-purple-400'  },
}

const COL_LABELS = [
  { x: 0,   label: 'Sources',      color: 'text-blue-400'   },
  { x: 2.5, label: 'Transforms',   color: 'text-amber-400'  },
  { x: 5,   label: 'Destinations', color: 'text-green-400'  },
  { x: 7.5, label: 'Consumers',    color: 'text-purple-400' },
]

// Grid constants
const COL_W  = 200   // pixels per x unit
const ROW_H  = 70    // pixels per y unit
const NODE_W = 160
const NODE_H = 52
const SVG_W  = 8.5 * COL_W
const SVG_H  = 8.5 * ROW_H

function nodeCenter(node) {
  return {
    x: node.x * COL_W + NODE_W / 2,
    y: node.y * ROW_H + NODE_H / 2,
  }
}

export default function DataLineageView() {
  const [selected, setSelected] = useState(null)
  const selectedNode = NODES.find(n => n.id === selected)

  const highlightedEdges = selected
    ? new Set(EDGES.filter(e => e.from === selected || e.to === selected).flatMap(e => [e.from, e.to]))
    : null

  return (
    <div className="flex flex-col gap-6 max-w-full pb-16 animate-fade-in">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <GitMerge className="w-5 h-5 text-cyan-400" />
            Data Lineage
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">End-to-end data flow from sources to consumers. Click any node to trace its lineage.</p>
        </div>
        {/* Legend */}
        <div className="flex items-center gap-3 flex-wrap">
          {Object.entries(TYPE_CFG).map(([type, cfg]) => (
            <span key={type} className="flex items-center gap-1.5 text-[10px] text-slate-400">
              <span className={`w-2 h-2 rounded-full ${cfg.dot}`} />
              {cfg.label}
            </span>
          ))}
        </div>
      </div>

      {/* Detail panel */}
      {selectedNode && (
        <div className={`flex items-start gap-3 p-4 rounded-2xl border ${TYPE_CFG[selectedNode.type].bg} relative`}>
          <span className="text-2xl">{selectedNode.icon}</span>
          <div className="flex-1 min-w-0">
            <p className={`text-sm font-bold ${TYPE_CFG[selectedNode.type].text}`}>{selectedNode.label}</p>
            <p className="text-xs text-slate-400">{selectedNode.sublabel} · Type: {TYPE_CFG[selectedNode.type].label}</p>
            <div className="flex flex-wrap gap-2 mt-2">
              <span className="text-[10px] text-slate-500">
                <strong className="text-slate-400">Upstream:</strong>{' '}
                {EDGES.filter(e => e.to === selectedNode.id).map(e => NODES.find(n => n.id === e.from)?.label).join(', ') || 'None'}
              </span>
              <span className="text-[10px] text-slate-500">
                <strong className="text-slate-400">Downstream:</strong>{' '}
                {EDGES.filter(e => e.from === selectedNode.id).map(e => NODES.find(n => n.id === e.to)?.label).join(', ') || 'None'}
              </span>
            </div>
          </div>
          <button onClick={() => setSelected(null)} className="text-slate-500 hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Column headers */}
      <div className="overflow-x-auto rounded-2xl border border-border bg-card p-4">
        <div className="relative" style={{ minWidth: SVG_W, minHeight: SVG_H + 40 }}>

          {/* Column header labels */}
          {COL_LABELS.map(col => (
            <div
              key={col.x}
              className={`absolute top-0 text-[10px] font-bold uppercase tracking-widest ${col.color}`}
              style={{ left: col.x * COL_W, width: NODE_W, textAlign: 'center' }}
            >
              {col.label}
            </div>
          ))}

          {/* SVG for edges */}
          <svg
            style={{ position: 'absolute', top: 28, left: 0, pointerEvents: 'none' }}
            width={SVG_W}
            height={SVG_H}
          >
            <defs>
              <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#475569" />
              </marker>
              <marker id="arrow-hi" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#6366f1" />
              </marker>
            </defs>
            {EDGES.map((edge, i) => {
              const from = NODES.find(n => n.id === edge.from)
              const to   = NODES.find(n => n.id === edge.to)
              if (!from || !to) return null
              const f = nodeCenter(from)
              const t = nodeCenter(to)
              const isHi = highlightedEdges && (highlightedEdges.has(edge.from) && highlightedEdges.has(edge.to))
              const mx = (f.x + t.x) / 2
              return (
                <g key={i}>
                  <path
                    d={`M${f.x + NODE_W / 2 - 4},${f.y} C${mx + 20},${f.y} ${mx - 20},${t.y} ${t.x - NODE_W / 2 + 4},${t.y}`}
                    fill="none"
                    stroke={isHi ? '#6366f1' : '#334155'}
                    strokeWidth={isHi ? 2 : 1.5}
                    markerEnd={isHi ? 'url(#arrow-hi)' : 'url(#arrow)'}
                    strokeDasharray={isHi ? '0' : '4 2'}
                    opacity={highlightedEdges && !isHi ? 0.2 : 1}
                  />
                  <text
                    x={mx}
                    y={(f.y + t.y) / 2 - 4}
                    textAnchor="middle"
                    className="text-[8px]"
                    style={{ fontSize: 9, fill: isHi ? '#818cf8' : '#475569' }}
                  >
                    {edge.label}
                  </text>
                </g>
              )
            })}
          </svg>

          {/* Nodes */}
          {NODES.map(node => {
            const cfg = TYPE_CFG[node.type]
            const isSelected  = selected === node.id
            const isHighlighted = highlightedEdges?.has(node.id)
            const isDimmed    = highlightedEdges && !isHighlighted
            return (
              <button
                key={node.id}
                onClick={() => setSelected(selected === node.id ? null : node.id)}
                className={`absolute flex items-center gap-2 px-3 rounded-xl border text-left transition-all cursor-pointer
                  ${isSelected ? `${cfg.bg} ring-2 ring-offset-1 ring-offset-slate-900 ring-indigo-500` : cfg.bg}
                  hover:opacity-90`}
                style={{
                  left: node.x * COL_W,
                  top:  node.y * ROW_H + 28,
                  width: NODE_W,
                  height: NODE_H,
                  opacity: isDimmed ? 0.25 : 1,
                }}
              >
                <span className="text-lg shrink-0">{node.icon}</span>
                <div className="min-w-0">
                  <p className={`text-xs font-bold truncate ${cfg.text}`}>{node.label}</p>
                  <p className="text-[9px] text-slate-500 truncate">{node.sublabel}</p>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      <p className="text-[10px] text-slate-600 text-center">
        {NODES.length} nodes · {EDGES.length} data flows · Click a node to trace its lineage
      </p>
    </div>
  )
}
