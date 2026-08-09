/** Tool registry catalog keys used by the frontend Tool Registry UI. */
export const TOOL_TYPES = [
  { id: 'aws', label: 'AWS', category: 'cloud' },
  { id: 'gcp', label: 'GCP', category: 'cloud' },
  { id: 'azure', label: 'Azure', category: 'cloud' },
  { id: 'github', label: 'GitHub', category: 'source_control' },
  { id: 'gitlab', label: 'GitLab', category: 'source_control' },
  { id: 'jira', label: 'Jira', category: 'project_mgmt' },
  { id: 'confluence', label: 'Confluence', category: 'project_mgmt' },
  { id: 'servicenow', label: 'ServiceNow', category: 'project_mgmt' },
  { id: 'slack', label: 'Slack', category: 'comms' },
  { id: 'pagerduty', label: 'PagerDuty', category: 'comms' },
  { id: 'kubernetes', label: 'Kubernetes', category: 'infra' },
  { id: 'prometheus', label: 'Prometheus', category: 'monitoring' },
]

export default TOOL_TYPES
