import { GitBranch } from 'lucide-react'
import ConnectorReadView from './ConnectorReadView'

export default function ArgoCDView() {
  return (
    <ConnectorReadView
      title="Argo CD"
      toolLabel="ArgoCD"
      endpoint="/api/argocd/applications"
      icon={GitBranch}
      columns={[
        { key: 'name', label: 'Application' },
        { key: 'project', label: 'Project' },
        { key: 'health', label: 'Health' },
        { key: 'sync', label: 'Sync' },
        { key: 'revision', label: 'Revision' },
      ]}
    />
  )
}
