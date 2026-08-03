import {
  GitPullRequest,
  Activity,
  Bell,
  MessageSquare,
  Flame,
  GitBranch,
  Zap,
  Workflow,
} from 'lucide-react'
import HubPage from './HubPage'

const CONNECTORS = [
  { label: 'GitHub PRs', path: '/github/prs', icon: GitPullRequest, description: 'Open pull requests across connected repositories.' },
  { label: 'GitHub Actions', path: '/github/actions', icon: Activity, description: 'Workflow runs, statuses, and recent failures.' },
  { label: 'Live Pipelines', path: '/live-pipelines', icon: Workflow, description: 'Real-time view of running CI/CD pipelines.' },
  { label: 'Argo CD', path: '/argocd', icon: GitBranch, description: 'GitOps application sync status and health.' },
  { label: 'PagerDuty', path: '/pagerduty', icon: Bell, description: 'Incidents, schedules, and on-call rotations.' },
  { label: 'Slack', path: '/slack', icon: MessageSquare, description: 'Channel notifications and message routing.' },
  { label: 'Prometheus', path: '/prometheus', icon: Flame, description: 'Metrics, alert rules, and query explorer.' },
  { label: 'Outbound Webhook', path: '/outbound-webhook', icon: Zap, description: 'Send portal events to external endpoints.' },
]

export default function ConnectorsHubPage() {
  return (
    <HubPage
      title="Connectors"
      subtitle="Integrated tools and services connected to the portal"
      items={CONNECTORS}
    />
  )
}
