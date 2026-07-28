import { MessageSquare } from 'lucide-react'
import ConnectorReadView from './ConnectorReadView'

export default function SlackView() {
  return (
    <ConnectorReadView
      title="Slack"
      toolLabel="Slack"
      endpoint="/api/slack/channels"
      icon={MessageSquare}
      columns={[
        { key: 'name', label: 'Channel' },
        { key: 'id', label: 'ID' },
        { key: 'is_private', label: 'Private' },
        { key: 'num_members', label: 'Members' },
      ]}
    />
  )
}
