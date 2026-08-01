/**
 * Normalize FastAPI / proxy error bodies into a short user-facing string.
 * Never returns HTML, stack traces, or "[object Object]".
 */
export function formatErrorDetail(detail, fallback = 'Request failed') {
  if (detail == null || detail === '') return fallback
  if (typeof detail === 'string') {
    const t = detail.trim()
    if (!t) return fallback
    if (/^<!DOCTYPE|^<html/i.test(t) || t.includes('<title>')) {
      return fallback
    }
    // Prefer JSON-encoded FastAPI body if we got raw text
    if (t.startsWith('{') || t.startsWith('[')) {
      try {
        return formatErrorDetail(JSON.parse(t), fallback)
      } catch {
        /* keep string */
      }
    }
    return t.length > 280 ? `${t.slice(0, 277)}…` : t
  }
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      if (typeof d === 'string') return d
      if (d && typeof d === 'object') return d.msg || d.message || d.detail || null
      return null
    }).filter(Boolean)
    return parts.length ? parts.join('; ') : fallback
  }
  if (typeof detail === 'object') {
    if (typeof detail.message === 'string' && detail.message.trim()) return detail.message.trim()
    if (typeof detail.detail === 'string' && detail.detail.trim()) return detail.detail.trim()
    if (typeof detail.error === 'string' && detail.error.trim()) return detail.error.trim()
    if (typeof detail.msg === 'string' && detail.msg.trim()) return detail.msg.trim()
    try {
      const s = JSON.stringify(detail)
      return s.length > 280 ? `${s.slice(0, 277)}…` : s
    } catch {
      return fallback
    }
  }
  return String(detail)
}

/**
 * Read a failed Response and return a safe error message.
 * Consumes the body (clone first if you still need it).
 */
export async function parseApiError(res, fallback = 'Request failed') {
  if (!res) return fallback
  const statusFallback =
    res.status === 401
      ? 'Unauthorized'
      : res.status === 403
        ? 'Forbidden'
        : res.status === 404
          ? 'Not found'
          : res.status === 429
            ? 'Too many requests — try again shortly'
            : res.status >= 500
              ? 'Server error — try again'
              : `${fallback} (${res.status || '?'})`

  try {
    const text = await res.text()
    if (!text || !text.trim()) return statusFallback
    try {
      const data = JSON.parse(text)
      return formatErrorDetail(data?.detail ?? data?.error ?? data?.message ?? data, statusFallback)
    } catch {
      return formatErrorDetail(text, statusFallback)
    }
  } catch {
    return statusFallback
  }
}

/** Map common connector failure phrases to short operator guidance. */
export function mapConnectionError(raw) {
  const msg = formatErrorDetail(raw, 'Connection failed')
  const lower = msg.toLowerCase()
  if (/401|unauthorized|bad credentials|invalid.*(token|pat|key)/.test(lower)) {
    return 'Invalid credentials — check the token in Tool Registry (value is never shown after save).'
  }
  if (/403|forbidden|insufficient.*(scope|permission)/.test(lower)) {
    return 'Token lacks required permissions for this tool.'
  }
  if (/404|not found/.test(lower)) {
    return 'Resource not found — verify account identifier / instance URL.'
  }
  if (/timeout|timed out|econnrefused|network|dns|enotfound/.test(lower)) {
    return 'Could not reach the provider — check network and instance URL.'
  }
  if (/rate.?limit|429/.test(lower)) {
    return 'Provider rate limit — retry in a few minutes.'
  }
  // Never echo obvious secrets/tokens into the UI
  if (/\b(ghp_|gho_|github_pat_|sk-|xox[baprs]-)[a-zA-Z0-9_-]+|pd\+[a-z0-9]+/i.test(msg)) {
    return 'Connection failed — credentials were rejected (token redacted).'
  }
  return msg.length > 160 ? `${msg.slice(0, 157)}…` : msg
}

/** Production-safe login message (no HTML / stack / internal dumps). */
export function safeLoginError(message, { isProd = false } = {}) {
  const msg = formatErrorDetail(message, 'Login failed')
  if (/^<!DOCTYPE|^<html/i.test(msg) || msg.includes('Traceback')) {
    return 'Login failed. Check your credentials and try again.'
  }
  if (isProd) {
    const allowed =
      /invalid|incorrect|credentials|password|username|mfa|totp|locked|disabled|forbidden|too many|rate/i
    if (!allowed.test(msg) && msg.length > 80) {
      return 'Login failed. Check your credentials and try again.'
    }
  }
  return msg
}
