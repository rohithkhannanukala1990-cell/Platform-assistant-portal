/** Mutable portal API headers (synced from OpsPortal context). Merged into authFetch. */
let _state = {
  activeEnvironment: 'development',
  activeWorkspaceId: null,
}

export function setPortalContextHeaders(updates) {
  _state = { ..._state, ...updates }
}

export function getPortalContextHeaders() {
  return {
    'X-Active-Environment': _state.activeEnvironment || 'development',
    'X-Workspace-Id': _state.activeWorkspaceId || 'default',
    'X-User-Id': 'admin',
  }
}
