/** Shared API / domain types for typed frontend modules. */

export type PortalRole = string | null

export interface AuthUser {
  id?: string | number
  username?: string
  name?: string
  email?: string
  role?: string | null
  tenant_id?: string | null
  workspace_id?: string | null
  [key: string]: unknown
}

export interface LoginResult {
  success: boolean
  error?: string
  role?: string | null
  mfaRequired?: boolean
  mfaEnrollmentRequired?: boolean
}

export interface LlmUsageRow {
  user_id?: string
  provider?: string
  model?: string
  source?: string
  tokens?: number
  calls?: number
  estimated_cost_usd?: number
  date?: string
  cost_usd?: number
}

export interface LlmBudgetRow {
  config_id?: number | null
  provider?: string
  model?: string
  monthly_token_budget?: number
  tokens_used_this_month?: number
  is_active?: boolean
}

export interface LlmUsageReport {
  days?: number
  tenant_id?: string
  total_tokens?: number
  prompt_tokens?: number
  completion_tokens?: number
  estimated_cost_usd?: number
  calls?: number
  by_provider?: LlmUsageRow[]
  by_model?: LlmUsageRow[]
  by_user?: LlmUsageRow[]
  by_source?: LlmUsageRow[]
  by_day?: LlmUsageRow[]
  budget?: LlmBudgetRow[]
}

export interface GithubRepo {
  full_name?: string
  name?: string
  owner?: string | { login?: string }
}

export interface GithubWorkflowRun {
  id: number | string
  name?: string
  status?: string
  conclusion?: string | null
  html_url?: string
  created_at?: string
  updated_at?: string
  head_branch?: string
  head_sha?: string
  event?: string
  display_title?: string
  run_attempt?: number
  actor?: string | { login?: string }
  path?: string
}

export interface ArgoApplication {
  name?: string
  namespace?: string
  project?: string
  health?: string
  sync?: string
  revision?: string
}

export type DeploymentStatus = 'success' | 'failed' | 'running' | 'cancelled' | 'unknown'

export interface DeploymentRow {
  id: string
  service: string
  version: string
  env: string
  status: DeploymentStatus
  triggeredBy: string
  commit: string
  message: string
  duration: string
  time: string
  htmlUrl?: string
  source: 'github' | 'argocd'
  rawStatus?: string
  rawConclusion?: string | null
}
