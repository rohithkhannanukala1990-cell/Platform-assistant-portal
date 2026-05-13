/**
 * API origin for browser fetches.
 * In Vite dev, default to same-origin so requests go through `vite.config.js` proxy
 * (avoids CORS and works for both localhost and 127.0.0.1).
 */
const envUrl = import.meta.env.VITE_API_BASE_URL
const trimmed = envUrl != null && String(envUrl).trim() !== '' ? String(envUrl).replace(/\/$/, '') : ''

export const API_BASE =
  trimmed || (import.meta.env.DEV ? '' : 'http://localhost:8000')
