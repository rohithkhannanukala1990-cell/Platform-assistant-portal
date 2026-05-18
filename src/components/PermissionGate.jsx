import { useAuth } from '../contexts/AuthContext'
import { useRole } from '../contexts/RoleContext'
import { usePermissions } from '../hooks/usePermissions'

/**
 * Portal JWT roles (AuthContext / RoleContext): Admin, Developer, DataEngineer,
 * NetworkEngineer, DatabaseDeveloper.
 * RBAC API roles (rbac.py seeds): viewer, operator, admin, superadmin — resource:action grants.
 */
const ROLE_RANK = {
  Viewer: 0,
  viewer: 0,
  DatabaseDeveloper: 0,
  Developer: 1,
  developer: 1,
  DataEngineer: 1,
  DevOps: 2,
  Operator: 2,
  operator: 2,
  NetworkEngineer: 2,
  Admin: 3,
  admin: 3,
  superadmin: 4,
  'Super Admin': 4,
}

const ADMIN_ONLY = ['rbac', 'account-import', 'tool-registry-write']

const DEVOPS_PLUS = ['infra', 'cicd-write', 'deployments-write', 'workspaces-write']

function roleRank(role) {
  if (!role) return 0
  const key = String(role).trim()
  if (ROLE_RANK[key] !== undefined) return ROLE_RANK[key]
  const lower = key.toLowerCase()
  if (ROLE_RANK[lower] !== undefined) return ROLE_RANK[lower]
  return 0
}

export function hasPermission(userRole, requiredRole) {
  const req = roleRank(requiredRole)
  if (req === 0 && requiredRole && !ROLE_RANK[String(requiredRole).trim()]) {
    return false
  }
  return roleRank(userRole) >= req
}

function isElevatedAdmin(role) {
  return roleRank(role) >= roleRank('Admin')
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
          ? `Requires ${requiredRole} role or above`
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
  const { role: jwtRole, user } = useAuth()
  const { role: contextRole } = useRole()
  const { can } = usePermissions()

  const effectiveRole = jwtRole || contextRole || user?.role || 'Viewer'

  let allowed = true

  if (resource && action) {
    allowed = isElevatedAdmin(effectiveRole) || can(resource, action)
  } else if (resource) {
    if (ADMIN_ONLY.includes(resource)) {
      allowed = isElevatedAdmin(effectiveRole)
    } else if (DEVOPS_PLUS.includes(resource)) {
      allowed = roleRank(effectiveRole) >= roleRank('Operator')
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
