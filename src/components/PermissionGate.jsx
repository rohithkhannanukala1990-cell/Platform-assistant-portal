import { usePermissions } from '../hooks/usePermissions'

export function PermissionGate({ resource, action, fallback = null, children }) {
  const { can } = usePermissions()
  if (!can(resource, action)) return fallback
  return children
}
