import { Database, Share2, Search, ScanSearch, HardDrive } from 'lucide-react'
import HubPage from './HubPage'

const DATA_TOOLS = [
  { label: 'Schema Browser', path: '/schema-browser', icon: Database, description: 'Explore database schemas, tables, and columns.' },
  { label: 'Data Lineage', path: '/data-lineage', icon: Share2, description: 'Trace how data flows between systems and jobs.' },
  { label: 'DB Analyzer', path: '/db-analyzer', icon: ScanSearch, description: 'Analyze database health and performance issues.' },
  { label: 'Query Analyzer', path: '/query-analyzer', icon: Search, description: 'Inspect slow queries and execution plans.' },
  { label: 'Storage', path: '/storage', icon: HardDrive, description: 'Buckets, volumes, and storage utilization.' },
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
