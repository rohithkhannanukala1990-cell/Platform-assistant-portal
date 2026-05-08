import { useState } from 'react'
import {
  BookOpen, Play, CheckCircle2, Clock, Tag, ChevronDown,
  ChevronUp, Terminal, Loader2, Shield, Server, Database,
  Wifi, Search,
} from 'lucide-react'

const CATEGORIES = ['All', 'Application', 'Database', 'Network', 'Security']

const CATEGORY_CFG = {
  Application: { icon: Server,   color: 'text-blue-400',   bg: 'bg-blue-500/10  border-blue-500/25'  },
  Database:    { icon: Database, color: 'text-cyan-400',   bg: 'bg-cyan-500/10  border-cyan-500/25'  },
  Network:     { icon: Wifi,     color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/25' },
  Security:    { icon: Shield,   color: 'text-red-400',    bg: 'bg-red-500/10   border-red-500/25'   },
}

const SEV_CFG = {
  Critical: 'text-red-400    bg-red-500/10    border-red-500/25',
  High:     'text-orange-400 bg-orange-500/10 border-orange-500/25',
  Medium:   'text-yellow-400 bg-yellow-500/10 border-yellow-500/25',
  Low:      'text-blue-400   bg-blue-500/10   border-blue-500/25',
}

const RUNBOOKS = [
  {
    id: 'rb-001',
    title: 'High Memory Usage — JVM Services',
    category: 'Application',
    severity: 'High',
    estimatedTime: '8 min',
    description: 'Diagnose and remediate memory leaks in Java-based microservices. Triggers heap dump, analyzes GC pressure, and restarts if OOM is imminent.',
    tags: ['jvm', 'memory', 'oom'],
    steps: [
      'Check pod memory usage: kubectl top pods -n production',
      'Capture heap dump: kubectl exec <pod> -- jcmd 1 GC.heap_dump /tmp/heap.hprof',
      'Analyze GC logs: kubectl logs <pod> --tail=200 | grep -i gc',
      'If OOM > 95%, trigger rolling restart: kubectl rollout restart deployment/<name>',
      'Verify services recover: kubectl rollout status deployment/<name>',
    ],
  },
  {
    id: 'rb-002',
    title: 'PostgreSQL Deadlock Resolution',
    category: 'Database',
    severity: 'Critical',
    estimatedTime: '5 min',
    description: 'Identify and terminate blocking transactions on the primary PostgreSQL instance to restore normal query execution.',
    tags: ['postgres', 'deadlock', 'blocking'],
    steps: [
      'Connect to primary: psql -h prod-postgres-primary -U postgres -d aiops',
      "Identify blockers: SELECT pid, query, state, wait_event FROM pg_stat_activity WHERE state != 'idle';",
      'Terminate the blocking PID: SELECT pg_terminate_backend(<blocking_pid>);',
      'Verify deadlock resolved: SELECT count(*) FROM pg_locks WHERE NOT granted;',
      'Alert the team and log the incident in Jira.',
    ],
  },
  {
    id: 'rb-003',
    title: 'High Latency — API Gateway',
    category: 'Network',
    severity: 'High',
    estimatedTime: '10 min',
    description: 'Investigate elevated P99 latency on the API gateway by checking upstream service health, connection pools, and rate limits.',
    tags: ['api-gateway', 'latency', 'p99'],
    steps: [
      'Check current P99: kubectl exec -it <pod> -- curl localhost:9090/metrics | grep latency',
      'Identify slow upstreams from access logs: kubectl logs -l app=api-gateway --tail=500 | grep "5[0-9][0-9]"',
      'Check connection pool exhaustion: kubectl exec <pod> -- env | grep POOL',
      'Temporarily increase pool size and reload config: kubectl rollout restart deployment/api-gateway',
      'Verify latency returns to baseline in Datadog.',
    ],
  },
  {
    id: 'rb-004',
    title: 'SSL Certificate Expiry',
    category: 'Security',
    severity: 'Critical',
    estimatedTime: '15 min',
    description: 'Renew expiring TLS certificates using cert-manager and validate all ingress endpoints are serving valid certs.',
    tags: ['ssl', 'tls', 'certificates'],
    steps: [
      'List expiring certs: kubectl get certificates -A | grep -v True',
      'Force renewal: kubectl delete secret <tls-secret-name> -n production',
      'cert-manager will auto-reissue — watch: kubectl describe certificate <name> -n production',
      'Verify new cert: openssl s_client -connect api.internal.corp:443 -servername api.internal.corp 2>/dev/null | openssl x509 -noout -dates',
      'Update cert expiry tracking in Confluence.',
    ],
  },
  {
    id: 'rb-005',
    title: 'Kafka Consumer Lag Spike',
    category: 'Application',
    severity: 'Medium',
    estimatedTime: '12 min',
    description: 'Diagnose consumer group lag in Kafka topics and scale consumers or reset offsets to catch up.',
    tags: ['kafka', 'consumer-lag', 'streaming'],
    steps: [
      'Check lag: kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group <group>',
      'Identify slow partitions and check consumer logs for errors.',
      'Scale consumer deployment: kubectl scale deployment/<consumer> --replicas=5',
      'If lag is unrecoverable, reset offset: kafka-consumer-groups.sh --reset-offsets --to-latest --execute --group <group> --topic <topic>',
      'Monitor lag reduction over next 15 minutes.',
    ],
  },
  {
    id: 'rb-006',
    title: 'DDoS / Rate Limit Breach',
    category: 'Security',
    severity: 'Critical',
    estimatedTime: '6 min',
    description: 'Detect and block abusive IPs that are breaching rate limits or triggering WAF alerts.',
    tags: ['ddos', 'rate-limit', 'waf'],
    steps: [
      'Identify top offenders: kubectl logs -l app=api-gateway --tail=1000 | awk \'{print $1}\' | sort | uniq -c | sort -rn | head -20',
      'Block via iptables: iptables -A INPUT -s <offending_ip> -j DROP',
      'Update WAF blocklist in Cloudflare dashboard.',
      'Increase rate limit threshold temporarily if legitimate traffic.',
      'File post-mortem and add IP to permanent blocklist.',
    ],
  },
]

function RunbookCard({ rb }) {
  const [expanded, setExpanded] = useState(false)
  const [running,  setRunning]  = useState(false)
  const [done,     setDone]     = useState(false)
  const [step,     setStep]     = useState(0)

  const catCfg  = CATEGORY_CFG[rb.category]
  const CatIcon = catCfg.icon

  function handleRun() {
    setRunning(true)
    setStep(0)
    setDone(false)
    const interval = setInterval(() => {
      setStep(prev => {
        if (prev >= rb.steps.length - 1) {
          clearInterval(interval)
          setRunning(false)
          setDone(true)
          return prev
        }
        return prev + 1
      })
    }, 900)
  }

  return (
    <div className={`flex flex-col rounded-2xl border overflow-hidden transition-all
      ${done ? 'border-green-500/25' : 'border-border'} bg-card`}>

      {/* Header */}
      <div className="flex items-start gap-3 p-4">
        <div className={`flex items-center justify-center w-9 h-9 rounded-xl border shrink-0 ${catCfg.bg}`}>
          <CatIcon className={`w-4 h-4 ${catCfg.color}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-sm font-bold text-white">{rb.title}</span>
            <span className={`text-[10px] px-2 py-0.5 rounded-md border font-semibold ${SEV_CFG[rb.severity]}`}>
              {rb.severity}
            </span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">{rb.description}</p>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <span className="flex items-center gap-1 text-[10px] text-slate-500">
              <Clock className="w-2.5 h-2.5" /> ~{rb.estimatedTime}
            </span>
            <span className={`text-[10px] px-2 py-0.5 rounded-md border font-semibold ${catCfg.bg} ${catCfg.color}`}>
              {rb.category}
            </span>
            {rb.tags.map(t => (
              <span key={t} className="flex items-center gap-1 text-[10px] text-slate-600 border border-slate-700 rounded-md px-1.5 py-0.5">
                <Tag className="w-2 h-2" />{t}
              </span>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {!done && (
            <button
              onClick={handleRun}
              disabled={running}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-accent/15 border border-accent/35
                text-accent text-xs font-bold hover:bg-accent/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {running
                ? <><Loader2 className="w-3 h-3 animate-spin" /> Running…</>
                : <><Play className="w-3 h-3" /> Run</>
              }
            </button>
          )}
          {done && (
            <span className="flex items-center gap-1 text-[11px] text-green-400 font-semibold">
              <CheckCircle2 className="w-3.5 h-3.5" /> Complete
            </span>
          )}
          <button
            onClick={() => setExpanded(v => !v)}
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-500 hover:text-white transition-colors"
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Steps */}
      {(expanded || running || done) && (
        <div className="border-t border-border px-4 pb-4 pt-3 flex flex-col gap-2">
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Execution Steps</p>
          <ol className="flex flex-col gap-1.5">
            {rb.steps.map((s, i) => {
              const isCurrent = running && i === step
              const isDone    = done || (running && i < step)
              return (
                <li key={i} className={`flex items-start gap-2 text-xs transition-all
                  ${isCurrent ? 'text-accent' : isDone ? 'text-green-400' : 'text-slate-500'}`}>
                  <span className={`shrink-0 mt-0.5 w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold border
                    ${isCurrent ? 'border-accent/50 bg-accent/15' : isDone ? 'border-green-500/40 bg-green-500/10' : 'border-slate-700 bg-transparent'}`}>
                    {isDone ? '✓' : i + 1}
                  </span>
                  <span className={`font-mono leading-relaxed ${s.startsWith('SELECT') || s.startsWith('kubectl') || s.startsWith('psql') || s.startsWith('kafka') || s.startsWith('openssl') || s.startsWith('iptables')
                    ? 'text-[10px] bg-black/40 border border-slate-700/60 rounded px-2 py-0.5 w-full' : ''}`}>
                    {s}
                  </span>
                </li>
              )
            })}
          </ol>
        </div>
      )}
    </div>
  )
}

export default function RunbooksView() {
  const [category, setCategory] = useState('All')
  const [search,   setSearch]   = useState('')

  const filtered = RUNBOOKS.filter(rb => {
    const matchCat    = category === 'All' || rb.category === category
    const matchSearch = !search || rb.title.toLowerCase().includes(search.toLowerCase()) ||
      rb.tags.some(t => t.includes(search.toLowerCase()))
    return matchCat && matchSearch
  })

  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto pb-16 animate-fade-in">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-blue-400" />
            Runbooks
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Executable step-by-step remediation playbooks</p>
        </div>
        <span className="text-[10px] text-slate-600 border border-slate-700 rounded-lg px-2.5 py-1 font-semibold">
          {filtered.length} runbooks
        </span>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Search */}
        <div className="flex items-center gap-2 bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 flex-1 min-w-48">
          <Search className="w-3.5 h-3.5 text-slate-500 shrink-0" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by title or tag…"
            className="bg-transparent text-xs text-slate-200 placeholder-slate-600 outline-none w-full"
          />
        </div>
        {/* Category pills */}
        <div className="flex items-center gap-2 flex-wrap">
          {CATEGORIES.map(cat => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold border transition-colors ${
                category === cat
                  ? 'bg-accent/15 border-accent/40 text-accent'
                  : 'border-slate-700 text-slate-500 hover:text-white hover:border-slate-600'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Runbook cards */}
      <div className="flex flex-col gap-4">
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-slate-600 text-sm">
            No runbooks match your filter.
          </div>
        ) : filtered.map(rb => <RunbookCard key={rb.id} rb={rb} />)}
      </div>
    </div>
  )
}
