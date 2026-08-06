/** Formatting helpers for LLM token utilization reports (pure / testable). */

export function formatUsdCost(value: unknown, digits = 4): string {
  const n = Number(value)
  if (!Number.isFinite(n)) return '$0.0000'
  return `$${n.toFixed(digits)}`
}

export function formatTokenCount(value: unknown): string {
  const n = Number(value)
  if (!Number.isFinite(n)) return '0'
  return Math.max(0, Math.round(n)).toLocaleString()
}

export function budgetUsagePct(used: unknown, budget: unknown): number {
  const u = Number(used) || 0
  const b = Number(budget) || 0
  if (b <= 0) return 0
  return Math.min(100, Math.round((u / b) * 100))
}

export type BudgetBarTone = 'ok' | 'warn' | 'critical'

export function budgetBarTone(pct: number): BudgetBarTone {
  if (pct >= 90) return 'critical'
  if (pct >= 70) return 'warn'
  return 'ok'
}
