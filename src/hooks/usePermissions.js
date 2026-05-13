import { useContext, useCallback } from 'react'
import { PortalContext } from '../contexts/PortalContext'

export function usePermissions() {
  const ctx = useContext(PortalContext)
  const currentUser = ctx?.currentUser ?? null

  const can = useCallback(
    (resource, action) => {
      if (!currentUser) return false
      if (currentUser.role === 'superadmin') return true
      const perms = currentUser.permissions || []
      return (
        perms.includes(`${resource}:${action}`) ||
        perms.includes(`${resource}:*`) ||
        perms.includes('*:*')
      )
    },
    [currentUser]
  )

  const canAny = useCallback(
    (resource, actions = []) => actions.some((a) => can(resource, a)),
    [can]
  )

  const isAdmin = useCallback(() => {
    return (
      can('roles', 'manage') ||
      currentUser?.role === 'admin' ||
      currentUser?.role === 'superadmin'
    )
  }, [can, currentUser])

  return { can, canAny, isAdmin }
}
