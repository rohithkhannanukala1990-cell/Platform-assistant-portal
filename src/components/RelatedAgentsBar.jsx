import { Link, useNavigate } from 'react-router-dom'
import { Bot } from 'lucide-react'

/** Map portal surfaces → related specialist agents + suggested task. */
export const SURFACE_AGENTS = {
  infra: [
    { agent: 'infra_agent', label: 'Infra', task: 'Propose infrastructure changes for the selected cloud provider' },
    { agent: 'cost_agent', label: 'Cost', task: 'Estimate cloud cost impact for planned infrastructure' },
    { agent: 'security_agent', label: 'Security', task: 'Review infra plan for security misconfigurations' },
  ],
  catalog: [
    { agent: 'catalog_health_agent', label: 'Catalog health', task: 'Assess catalog entity completeness and health' },
    { agent: 'scorecard_agent', label: 'Scorecard', task: 'Evaluate scorecard checks for the selected entity' },
    { agent: 'documentation_agent', label: 'Docs', task: 'Suggest documentation improvements for this service' },
    { agent: 'onboarding_agent', label: 'Onboarding', task: 'Generate onboarding steps for this catalog entity' },
    { agent: 'dependency_drift_agent', label: 'Deps', task: 'Check dependency drift for this service' },
  ],
  scorecards: [
    { agent: 'scorecard_agent', label: 'Scorecard', task: 'Evaluate and summarize scorecard evidence' },
    { agent: 'catalog_health_agent', label: 'Catalog health', task: 'Correlate scorecard gaps with catalog health' },
  ],
  github_prs: [
    { agent: 'code_review_agent', label: 'Code review', task: 'Review the selected pull request with live GitHub evidence' },
    { agent: 'security_agent', label: 'Security', task: 'Scan PR changes for security issues' },
    { agent: 'tester_agent', label: 'Tester', task: 'Suggest tests for the open PR' },
  ],
  github_actions: [
    { agent: 'pipeline_monitor_agent', label: 'Pipeline', task: 'Diagnose the latest failed GitHub Actions workflow' },
    { agent: 'tester_agent', label: 'Tester', task: 'Summarize CI test failures from Actions' },
    { agent: 'deploy_agent', label: 'Deploy', task: 'Propose a safe deploy after green CI' },
  ],
  cicd: [
    { agent: 'pipeline_monitor_agent', label: 'Pipeline', task: 'Monitor CI/CD pipelines and report failures' },
    { agent: 'deploy_agent', label: 'Deploy', task: 'Propose deployment steps for the selected service' },
  ],
  deployments: [
    { agent: 'deploy_agent', label: 'Deploy', task: 'Plan and dry-run a production deployment' },
    { agent: 'pipeline_monitor_agent', label: 'Pipeline', task: 'Check pipeline status before deploy' },
  ],
  incidents: [
    { agent: 'incident_agent', label: 'Incident', task: 'Triage the open incident with available evidence' },
    { agent: 'runbook_agent', label: 'Runbook', task: 'Find runbooks matching this incident' },
    { agent: 'auto_heal_agent', label: 'Auto-heal', task: 'Suggest low-risk auto-heal actions' },
  ],
  health: [
    { agent: 'auto_heal_agent', label: 'Auto-heal', task: 'Propose low-risk auto-heal for unhealthy services' },
    { agent: 'alert_noise_agent', label: 'Alert noise', task: 'Identify noisy alerts and suppress/group rules' },
  ],
  runbooks: [
    { agent: 'runbook_agent', label: 'Runbook', task: 'Match runbooks to the current incident or service' },
    { agent: 'documentation_agent', label: 'Docs', task: 'Improve runbook documentation quality' },
  ],
  dependencies: [
    { agent: 'dependency_drift_agent', label: 'Deps drift', task: 'Detect dependency drift across catalog services' },
    { agent: 'catalog_health_agent', label: 'Catalog health', task: 'Check catalog health for dependency owners' },
  ],
  pagerduty: [
    { agent: 'incident_agent', label: 'Incident', task: 'Triage PagerDuty-linked incidents' },
    { agent: 'alert_noise_agent', label: 'Alert noise', task: 'Reduce alert noise using PD context' },
  ],
  k8s: [
    { agent: 'infra_agent', label: 'Infra', task: 'Inspect Kubernetes resources and propose safe changes' },
    { agent: 'auto_heal_agent', label: 'Auto-heal', task: 'Suggest auto-heal for unhealthy pods/workloads' },
  ],
  tools: [
    { agent: 'onboarding_agent', label: 'Onboarding', task: 'Help connect and validate tool accounts' },
    { agent: 'security_agent', label: 'Security', task: 'Review tool connection security posture' },
  ],
}

export function agentRunnerState({ agents, task, entityId, entityName, extra = {} }) {
  const list = Array.isArray(agents) ? agents.filter(Boolean) : [agents].filter(Boolean)
  return {
    preselectAgents: list,
    prefillTask: task || '',
    entityId: entityId || null,
    entityName: entityName || null,
    focusRun: true,
    ...extra,
  }
}

/**
 * Compact chips linking to Agent Runner with preselected agents + task.
 */
export default function RelatedAgentsBar({
  surface,
  agents = null,
  task = null,
  entityId = null,
  entityName = null,
  className = '',
  title = 'Related agents',
}) {
  const navigate = useNavigate()
  const items = agents?.length ? agents : SURFACE_AGENTS[surface] || []

  if (!items.length) return null

  function openAgent(item) {
    navigate('/agents', {
      state: agentRunnerState({
        agents: [item.agent],
        task: task || item.task,
        entityId,
        entityName,
      }),
    })
  }

  return (
    <div
      className={`flex flex-wrap items-center gap-2 rounded-xl border border-indigo-500/25 bg-indigo-500/5 px-3 py-2 ${className}`}
      data-testid="related-agents-bar"
    >
      <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-indigo-300">
        <Bot className="w-3.5 h-3.5" />
        {title}
      </span>
      <div className="flex flex-wrap gap-1.5">
        {items.map((item) => (
          <button
            key={item.agent}
            type="button"
            onClick={() => openAgent(item)}
            title={item.task}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium
              border border-indigo-500/40 bg-indigo-600/20 text-indigo-100
              hover:bg-indigo-600/40 hover:border-indigo-400 transition-colors"
          >
            {item.label}
          </button>
        ))}
      </div>
      <Link
        to="/agents"
        className="ml-auto text-[11px] text-indigo-400 hover:text-indigo-200 underline-offset-2 hover:underline"
      >
        Open Agents →
      </Link>
    </div>
  )
}
