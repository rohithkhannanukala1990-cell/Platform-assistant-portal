import type {
  ArgoApplication,
  DeploymentRow,
  DeploymentStatus,
  GithubWorkflowRun,
} from '../types/api'

function actorLogin(actor: GithubWorkflowRun['actor']): string {
  if (!actor) return 'unknown'
  if (typeof actor === 'string') return actor
  return actor.login || 'unknown'
}

function shortSha(sha?: string): string {
  if (!sha) return '—'
  return sha.slice(0, 7)
}

function relativeTime(iso?: string): string {
  if (!iso) return '—'
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return iso
  const delta = Date.now() - t
  const mins = Math.round(delta / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  if (hours < 48) return `${hours} h ago`
  const days = Math.round(hours / 24)
  return `${days} d ago`
}

function durationBetween(start?: string, end?: string): string {
  if (!start || !end) return '—'
  const a = Date.parse(start)
  const b = Date.parse(end)
  if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return '—'
  const secs = Math.round((b - a) / 1000)
  if (secs < 60) return `${secs}s`
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return `${m}m ${String(s).padStart(2, '0')}s`
}

function inferEnv(branch?: string): string {
  const b = (branch || '').toLowerCase()
  if (b === 'main' || b === 'master' || b.includes('prod')) return 'production'
  if (b.includes('stag')) return 'staging'
  if (b.includes('test')) return 'test'
  if (b.includes('dev')) return 'dev'
  return branch || 'unknown'
}

export function mapGithubConclusion(
  status?: string,
  conclusion?: string | null
): DeploymentStatus {
  const s = (status || '').toLowerCase()
  const c = (conclusion || '').toLowerCase()
  if (s === 'in_progress' || s === 'queued' || s === 'pending' || s === 'waiting') {
    return 'running'
  }
  if (c === 'success') return 'success'
  if (c === 'failure' || c === 'timed_out' || c === 'startup_failure') return 'failed'
  if (c === 'cancelled' || c === 'skipped') return 'cancelled'
  if (s === 'completed' && !c) return 'unknown'
  return 'unknown'
}

/** Prefer deploy-ish workflow names; keep others so the page is still useful. */
export function isDeployishRun(run: GithubWorkflowRun): boolean {
  const blob = `${run.name || ''} ${run.path || ''} ${run.display_title || ''}`.toLowerCase()
  return /deploy|release|cd|production|staging|rollout|helm|argocd|k8s|kubernetes/.test(blob)
}

export function githubRunToDeployment(
  run: GithubWorkflowRun,
  repoFullName: string
): DeploymentRow {
  return {
    id: `gh-${run.id}`,
    service: repoFullName,
    version: shortSha(run.head_sha),
    env: inferEnv(run.head_branch),
    status: mapGithubConclusion(run.status, run.conclusion),
    triggeredBy: actorLogin(run.actor),
    commit: shortSha(run.head_sha),
    message: run.display_title || run.name || 'Workflow run',
    duration: durationBetween(run.created_at, run.updated_at),
    time: relativeTime(run.created_at),
    htmlUrl: run.html_url,
    source: 'github',
    rawStatus: run.status,
    rawConclusion: run.conclusion ?? null,
  }
}

export function argoAppToDeployment(app: ArgoApplication): DeploymentRow {
  const health = (app.health || '').toLowerCase()
  const sync = (app.sync || '').toLowerCase()
  let status: DeploymentStatus = 'unknown'
  if (sync === 'progressing' || health === 'progressing') status = 'running'
  else if (health === 'healthy' && (sync === 'synced' || sync === 'synced')) status = 'success'
  else if (health === 'degraded' || health === 'missing' || sync === 'outofsync') status = 'failed'
  else if (health === 'healthy') status = 'success'

  return {
    id: `argo-${app.name || 'app'}`,
    service: app.name || 'application',
    version: (app.revision || '—').slice(0, 12),
    env: app.namespace || app.project || 'default',
    status,
    triggeredBy: 'argocd',
    commit: (app.revision || '—').slice(0, 7),
    message: `health=${app.health || '?'} sync=${app.sync || '?'}`,
    duration: '—',
    time: '—',
    source: 'argocd',
    rawStatus: app.sync,
    rawConclusion: app.health,
  }
}

export function sortDeployments(rows: DeploymentRow[]): DeploymentRow[] {
  return [...rows].sort((a, b) => {
    // Prefer github rows with real timestamps first via id stability; keep API order mostly
    if (a.source !== b.source) return a.source === 'github' ? -1 : 1
    return 0
  })
}
