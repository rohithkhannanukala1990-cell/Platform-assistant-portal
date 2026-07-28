import { Activity } from 'lucide-react'
import ConnectorReadView from './ConnectorReadView'

export default function PrometheusView() {
  return (
    <ConnectorReadView
      title="Prometheus"
      toolLabel="Prometheus"
      endpoint="/api/prometheus/alerts"
      icon={Activity}
      columns={[
        { key: 'name', label: 'Alert' },
        { key: 'state', label: 'State' },
        { key: 'severity', label: 'Severity' },
        { key: 'service', label: 'Service' },
        { key: 'summary', label: 'Summary' },
      ]}
    />
  )
}
