import { Database, Share2, Search, ScanSearch, HardDrive } from 'lucide-react'
import HubPage from './HubPage'

const DATA_TOOLS = [
  { label: 'Schema Browser', path: '/schema-browser', icon: Database, preview: true, description: 'Explore database schemas, tables, and columns (sample data).' },
  { label: 'Data Lineage', path: '/data-lineage', icon: Share2, preview: true, description: 'Trace how data flows between systems and jobs (sample graph).' },
  { label: 'DB Analyzer', path: '/db-analyzer', icon: ScanSearch, preview: true, description: 'Analyze database health and performance issues (preview).' },
  { label: 'Query Analyzer', path: '/query-analyzer', icon: Search, preview: true, description: 'Inspect slow queries and execution plans (preview).' },
  { label: 'Storage', path: '/storage', icon: HardDrive, preview: true, description: 'Buckets, volumes, and storage utilization (sample data).' },
]

export default function DataToolsHubPage() {
  return (
    <HubPage
      title="Data Tools"
      subtitle="Databases, lineage, and storage utilities"
      items={DATA_TOOLS}
    />
  )
}
