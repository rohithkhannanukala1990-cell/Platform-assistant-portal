import { useAuth } from '../contexts/AuthContext'
import { usePermissions } from '../hooks/usePermissions'

/** Portal roles: Admin | User only */
const ROLE_RANK = {
  User: 0,
  Admin: 1,
  admin: 1,
}

const ADMIN_ONLY = ['rbac', 'account-import', 'tool-registry-write']

function roleRank(role) {
  if (!role) return 0
  const key = String(role).trim()
  if (ROLE_RANK[key] !== undefined) return ROLE_RANK[key]
  return key === 'Admin' ? 1 : 0
}

export function hasPermission(userRole, requiredRole) {
  if (requiredRole === 'Admin') return roleRank(userRole) >= 1
  return true
}

function isElevatedAdmin(role) {
  return roleRank(role) >= 1
}

function PermissionDenied({ requiredRole, resource }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-slate-500 gap-2">
      <span className="text-2xl" aria-hidden>
        🔒
      </span>
      <p className="text-sm font-medium">Permission Required</p>
      <p className="text-xs text-slate-600 text-center max-w-sm px-4">
        {requiredRole
          ? `Requires ${requiredRole} role`
          : resource
            ? `You do not have access to ${resource}`
            : 'You do not have access to this feature'}
      </p>
    </div>
  )
}

function PermissionGate({
  children,
  requiredRole,
  resource,
  action,
  fallback = null,
  showFallback = false,
}) {
  const { role, user } = useAuth()
  const { can } = usePermissions()

  const effectiveRole = role || user?.role || 'User'

  let allowed = true

  if (resource && action) {
    allowed = isElevatedAdmin(effectiveRole) || can(resource, action)
  } else if (resource) {
    if (ADMIN_ONLY.includes(resource)) {
      allowed = isElevatedAdmin(effectiveRole)
    }
  }

  if (requiredRole && allowed) {
    allowed = hasPermission(effectiveRole, requiredRole)
  }

  if (!allowed) {
    if (showFallback) {
      return <PermissionDenied requiredRole={requiredRole} resource={resource} />
    }
    return fallback
  }

  return children
}

export default PermissionGate
export { PermissionGate }
