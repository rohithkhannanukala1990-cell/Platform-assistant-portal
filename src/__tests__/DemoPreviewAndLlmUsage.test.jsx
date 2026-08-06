import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import DemoPreviewBanner from '../components/ui/DemoPreviewBanner'
import {
  budgetBarTone,
  budgetUsagePct,
  formatTokenCount,
  formatUsdCost,
} from '../utils/llmUsageFormat'

afterEach(() => {
  cleanup()
})

describe('DemoPreviewBanner', () => {
  it('marks preview surfaces clearly', () => {
    render(
      <DemoPreviewBanner title="Preview — sample deployments">
        Simulation only.
      </DemoPreviewBanner>
    )
    const banner = screen.getByTestId('demo-preview-banner')
    expect(banner).toHaveTextContent('Preview — sample deployments')
    expect(banner).toHaveTextContent('Simulation only.')
  })
})

describe('llmUsageFormat', () => {
  it('formats USD cost to fixed digits', () => {
    expect(formatUsdCost(0.123456)).toBe('$0.1235')
    expect(formatUsdCost(undefined)).toBe('$0.0000')
  })

  it('formats token counts', () => {
    expect(formatTokenCount(1500)).toBe('1,500')
    expect(formatTokenCount(null)).toBe('0')
  })

  it('computes budget usage percent and tone', () => {
    expect(budgetUsagePct(700, 1000)).toBe(70)
    expect(budgetUsagePct(950, 1000)).toBe(95)
    expect(budgetUsagePct(10, 0)).toBe(0)
    expect(budgetBarTone(70)).toBe('warn')
    expect(budgetBarTone(90)).toBe('critical')
    expect(budgetBarTone(20)).toBe('ok')
  })
})
