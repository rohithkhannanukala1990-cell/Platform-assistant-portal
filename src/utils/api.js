import { API_BASE } from '../config/apiBase'
import { getPortalContextHeaders } from './portalContextHeaders'

/**
 * Authenticated fetch for portal API calls (Bearer + portal context headers).
 * Prefer this over raw fetch in feature pages.
 */
export async function authFetch(url, options = {}) {
  const fullUrl = /^https?:\/\//i.test(url) ? url : `${API_BASE}${url}`
  const headers = new Headers(options.headers || {})
  let token = null
  try {
    token = localStorage.getItem('aiops_access_token')
  } catch {
    token = null
  }
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const portalHeaders = getPortalContextHeaders()
  Object.entries(portalHeaders || {}).forEach(([k, v]) => {
    if (v != null && v !== '') headers.set(k, String(v))
  })
  return fetch(fullUrl, { ...options, headers })
}
