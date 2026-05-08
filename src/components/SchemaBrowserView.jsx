import { useState } from 'react'
import { LayoutGrid, Key, Link, Search, Copy, Check, ChevronRight, Table2, Hash } from 'lucide-react'

const SCHEMA = {
  'prod-postgres-primary': [
    {
      name: 'users', rows: '2.4M', size: '1.2 GB', lastAnalyzed: '2 h ago',
      columns: [
        { name: 'id',            type: 'BIGSERIAL',    nullable: false, pk: true,  fk: null,                       default: null },
        { name: 'email',         type: 'VARCHAR(255)',  nullable: false, pk: false, fk: null,                       default: null },
        { name: 'password_hash', type: 'TEXT',          nullable: false, pk: false, fk: null,                       default: null },
        { name: 'created_at',    type: 'TIMESTAMPTZ',  nullable: false, pk: false, fk: null,                       default: 'NOW()' },
        { name: 'updated_at',    type: 'TIMESTAMPTZ',  nullable: false, pk: false, fk: null,                       default: 'NOW()' },
        { name: 'role',          type: 'VARCHAR(50)',   nullable: false, pk: false, fk: null,                       default: "'user'" },
        { name: 'org_id',        type: 'BIGINT',        nullable: true,  pk: false, fk: 'organisations.id',         default: null },
      ],
      indexes: ['users_pkey (id)', 'users_email_unique (email)', 'users_org_id_idx (org_id)'],
    },
    {
      name: 'incidents', rows: '142K', size: '340 MB', lastAnalyzed: '15 min ago',
      columns: [
        { name: 'id',             type: 'BIGSERIAL',   nullable: false, pk: true,  fk: null,         default: null },
        { name: 'title',          type: 'TEXT',         nullable: false, pk: false, fk: null,         default: null },
        { name: 'severity',       type: 'VARCHAR(20)',  nullable: false, pk: false, fk: null,         default: null },
        { name: 'status',         type: 'VARCHAR(30)',  nullable: false, pk: false, fk: null,         default: "'OPEN'" },
        { name: 'owner_role',     type: 'VARCHAR(50)',  nullable: true,  pk: false, fk: null,         default: "'Admin'" },
        { name: 'source',         type: 'TEXT',         nullable: true,  pk: false, fk: null,         default: "'manual'" },
        { name: 'raw_logs',       type: 'TEXT',         nullable: true,  pk: false, fk: null,         default: null },
        { name: 'timestamp',      type: 'TIMESTAMPTZ', nullable: false, pk: false, fk: null,         default: 'NOW()' },
        { name: 'user_id',        type: 'BIGINT',       nullable: true,  pk: false, fk: 'users.id',   default: null },
      ],
      indexes: ['incidents_pkey (id)', 'incidents_status_idx (status)', 'incidents_severity_idx (severity)', 'incidents_timestamp_idx (timestamp DESC)'],
    },
    {
      name: 'organisations', rows: '8.2K', size: '4 MB', lastAnalyzed: '1 d ago',
      columns: [
        { name: 'id',         type: 'BIGSERIAL',   nullable: false, pk: true,  fk: null, default: null },
        { name: 'name',       type: 'VARCHAR(255)', nullable: false, pk: false, fk: null, default: null },
        { name: 'plan',       type: 'VARCHAR(50)',  nullable: false, pk: false, fk: null, default: "'free'" },
        { name: 'created_at', type: 'TIMESTAMPTZ', nullable: false, pk: false, fk: null, default: 'NOW()' },
      ],
      indexes: ['organisations_pkey (id)', 'organisations_name_idx (name)'],
    },
    {
      name: 'sessions', rows: '18M', size: '3.8 GB', lastAnalyzed: '5 min ago',
      columns: [
        { name: 'id',         type: 'UUID',         nullable: false, pk: true,  fk: null,       default: 'gen_random_uuid()' },
        { name: 'user_id',    type: 'BIGINT',        nullable: false, pk: false, fk: 'users.id', default: null },
        { name: 'token_hash', type: 'TEXT',          nullable: false, pk: false, fk: null,       default: null },
        { name: 'expires_at', type: 'TIMESTAMPTZ',  nullable: false, pk: false, fk: null,       default: null },
        { name: 'created_at', type: 'TIMESTAMPTZ',  nullable: false, pk: false, fk: null,       default: 'NOW()' },
        { name: 'ip_address', type: 'INET',          nullable: true,  pk: false, fk: null,       default: null },
      ],
      indexes: ['sessions_pkey (id)', 'sessions_user_id_idx (user_id)', 'sessions_expires_at_idx (expires_at)'],
    },
    {
      name: 'notifications', rows: '891K', size: '180 MB', lastAnalyzed: '30 min ago',
      columns: [
        { name: 'id',          type: 'BIGSERIAL',   nullable: false, pk: true,  fk: null,             default: null },
        { name: 'message',     type: 'TEXT',         nullable: false, pk: false, fk: null,             default: null },
        { name: 'type',        type: 'VARCHAR(20)',  nullable: false, pk: false, fk: null,             default: null },
        { name: 'is_read',     type: 'BOOLEAN',      nullable: false, pk: false, fk: null,             default: 'false' },
        { name: 'incident_id', type: 'BIGINT',       nullable: true,  pk: false, fk: 'incidents.id',   default: null },
        { name: 'created_at',  type: 'TIMESTAMPTZ', nullable: false, pk: false, fk: null,             default: 'NOW()' },
      ],
      indexes: ['notifications_pkey (id)', 'notifications_is_read_idx (is_read)', 'notifications_incident_id_idx (incident_id)'],
    },
  ],
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  return (
    <button onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
      className="p-1.5 rounded-lg text-slate-500 hover:text-white hover:bg-slate-800 transition-colors">
      {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
    </button>
  )
}

function ddlFor(table) {
  const cols = table.columns.map(c => {
    let line = `  ${c.name.padEnd(20)} ${c.type}`
    if (c.pk)       line += ' PRIMARY KEY'
    if (!c.nullable && !c.pk) line += ' NOT NULL'
    if (c.default)  line += ` DEFAULT ${c.default}`
    if (c.fk)       line += ` REFERENCES ${c.fk}`
    return line
  }).join(',\n')
  return `CREATE TABLE ${table.name} (\n${cols}\n);`
}

export default function SchemaBrowserView() {
  const [dbKey,      setDbKey]      = useState('prod-postgres-primary')
  const [search,     setSearch]     = useState('')
  const [selected,   setSelected]   = useState(null)

  const tables = SCHEMA[dbKey] ?? []
  const filtered = tables.filter(t => t.name.includes(search.toLowerCase()))
  const selectedTable = tables.find(t => t.name === selected)

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-16 animate-fade-in">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <LayoutGrid className="w-5 h-5 text-cyan-400" />
            Schema Browser
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Explore tables, columns, types, foreign keys, and generate DDL</p>
        </div>
        <select
          value={dbKey}
          onChange={e => { setDbKey(e.target.value); setSelected(null) }}
          className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-cyan-500"
        >
          {Object.keys(SCHEMA).map(k => <option key={k} value={k}>{k}</option>)}
        </select>
      </div>

      <div className="flex gap-4" style={{ minHeight: 520 }}>

        {/* Table list */}
        <div className="flex flex-col gap-2 w-56 shrink-0">
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-700 rounded-xl px-3 py-2">
            <Search className="w-3 h-3 text-slate-500 shrink-0" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filter tables…"
              className="bg-transparent text-xs text-slate-200 placeholder-slate-600 outline-none w-full"
            />
          </div>
          <div className="flex flex-col gap-1">
            {filtered.map(t => (
              <button
                key={t.name}
                onClick={() => setSelected(t.name)}
                className={`flex items-center gap-2 px-3 py-2.5 rounded-xl text-left transition-colors w-full group
                  ${selected === t.name ? 'bg-cyan-500/10 border border-cyan-500/25' : 'hover:bg-card border border-transparent'}`}
              >
                <Table2 className={`w-3.5 h-3.5 shrink-0 ${selected === t.name ? 'text-cyan-400' : 'text-slate-500 group-hover:text-slate-300'}`} />
                <div className="min-w-0 flex-1">
                  <p className={`text-xs font-semibold truncate ${selected === t.name ? 'text-cyan-400' : 'text-slate-300'}`}>{t.name}</p>
                  <p className="text-[9px] text-slate-600">{t.rows} rows · {t.size}</p>
                </div>
                <ChevronRight className={`w-3 h-3 shrink-0 ${selected === t.name ? 'text-cyan-400' : 'text-slate-700'}`} />
              </button>
            ))}
          </div>
        </div>

        {/* Column detail */}
        <div className="flex-1 min-w-0">
          {!selectedTable ? (
            <div className="flex items-center justify-center h-full text-slate-600 text-sm rounded-2xl border border-dashed border-slate-800">
              Select a table to inspect its schema
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {/* Table meta */}
              <div className="flex items-center justify-between flex-wrap gap-2 px-4 py-3 rounded-xl border border-border bg-card">
                <div className="flex items-center gap-3">
                  <Table2 className="w-4 h-4 text-cyan-400" />
                  <div>
                    <p className="text-sm font-bold text-white">{selectedTable.name}</p>
                    <p className="text-[10px] text-slate-500">
                      {selectedTable.rows} rows · {selectedTable.size} · Last analyzed: {selectedTable.lastAnalyzed}
                    </p>
                  </div>
                </div>
                <CopyButton text={ddlFor(selectedTable)} />
              </div>

              {/* Columns table */}
              <div className="rounded-2xl border border-border overflow-hidden">
                <div className="grid grid-cols-[2fr_2fr_1fr_1fr_2fr] px-4 py-2.5 bg-slate-900 border-b border-border gap-2">
                  {['Column', 'Type', 'Nullable', 'Flags', 'Default / FK'].map(h => (
                    <span key={h} className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest">{h}</span>
                  ))}
                </div>
                {selectedTable.columns.map(col => (
                  <div key={col.name}
                    className="grid grid-cols-[2fr_2fr_1fr_1fr_2fr] items-center px-4 py-2.5 border-b border-border/50 last:border-0 gap-2 hover:bg-card/30 transition-colors">
                    <span className="text-xs font-mono font-semibold text-white">{col.name}</span>
                    <span className="text-xs font-mono text-cyan-400">{col.type}</span>
                    <span className={`text-[10px] font-semibold ${col.nullable ? 'text-slate-500' : 'text-red-400'}`}>
                      {col.nullable ? 'YES' : 'NO'}
                    </span>
                    <div className="flex items-center gap-1">
                      {col.pk && (
                        <span title="Primary Key" className="flex items-center gap-0.5 text-[9px] text-amber-400 bg-amber-500/10 border border-amber-500/25 rounded px-1 py-0.5 font-bold">
                          <Key className="w-2 h-2" />PK
                        </span>
                      )}
                      {col.fk && (
                        <span title={`Foreign Key → ${col.fk}`} className="flex items-center gap-0.5 text-[9px] text-blue-400 bg-blue-500/10 border border-blue-500/25 rounded px-1 py-0.5 font-bold">
                          <Link className="w-2 h-2" />FK
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono truncate" title={col.fk ?? col.default ?? ''}>
                      {col.fk ? `→ ${col.fk}` : col.default ?? '—'}
                    </div>
                  </div>
                ))}
              </div>

              {/* Indexes */}
              <div className="flex flex-col gap-2 p-4 rounded-2xl border border-border bg-card">
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
                  <Hash className="w-3 h-3" /> Indexes ({selectedTable.indexes.length})
                </p>
                <div className="flex flex-wrap gap-2">
                  {selectedTable.indexes.map(idx => (
                    <span key={idx} className="text-[10px] font-mono text-slate-400 bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1">
                      {idx}
                    </span>
                  ))}
                </div>
              </div>

              {/* DDL */}
              <div className="flex flex-col rounded-2xl border border-slate-700 overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2 bg-black/60 border-b border-slate-700">
                  <span className="text-[10px] font-mono text-slate-400">CREATE TABLE DDL</span>
                  <CopyButton text={ddlFor(selectedTable)} />
                </div>
                <pre className="px-4 py-3 bg-black/80 text-[10px] font-mono text-green-400 leading-relaxed overflow-x-auto whitespace-pre max-h-48">
                  {ddlFor(selectedTable)}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
