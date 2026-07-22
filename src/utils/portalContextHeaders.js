/** Mutable portal API headers (synced from PortalContext). Merged into authFetch. */
let _state = {
  activeEnvironment: 'development',
  activeWorkspaceId: null,
  activeTenantId: null,
}

export function setPortalContextHeaders(updates) {
  _state = { ..._state, ...updates }
}

export function getPortalContextHeaders() {
  // Demo / single-tenant: fall back to "default" workspace & tenant when unset.
  const workspaceId = _state.activeWorkspaceId || 'default'
  const tenantId = _state.activeTenantId || 'default'
  return {
    'X-Active-Environment': _state.activeEnvironment || 'development',
    'X-Workspace-Id': workspaceId,
    'X-Tenant-Id': tenantId,
    'X-User-Id': 'admin',
  }
}
