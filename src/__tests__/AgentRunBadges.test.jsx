import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import {
  AgentApproveRejectButtons,
  GroundingBadge,
} from '../components/agent/AgentRunBadges'
import {
  formatErrorDetail,
  mapConnectionError,
  safeLoginError,
} from '../utils/parseApiError'

afterEach(() => {
  cleanup()
})

describe('GroundingBadge', () => {
  it('renders live grounding badge', () => {
    render(<GroundingBadge grounding="live" />)
    const el = screen.getByTestId('grounding-badge')
    expect(el).toHaveTextContent('grounding: live')
    expect(el).toHaveAttribute('data-grounding', 'live')
  })

  it('defaults unknown grounding to none', () => {
    render(<GroundingBadge />)
    expect(screen.getByTestId('grounding-badge')).toHaveAttribute('data-grounding', 'none')
  })
})

describe('AgentApproveRejectButtons', () => {
  it('disables approve/reject while busy (pending HITL)', () => {
    render(
      <AgentApproveRejectButtons busy onApprove={() => {}} onReject={() => {}} />
    )
    expect(screen.getByTestId('approve-btn')).toBeDisabled()
    expect(screen.getByTestId('reject-btn')).toBeDisabled()
  })

  it('enables buttons when not busy', () => {
    render(
      <AgentApproveRejectButtons busy={false} onApprove={() => {}} onReject={() => {}} />
    )
    expect(screen.getByTestId('approve-btn')).not.toBeDisabled()
    expect(screen.getByTestId('reject-btn')).not.toBeDisabled()
  })
})

describe('parseApiError helpers', () => {
  it('formatErrorDetail never returns [object Object]', () => {
    expect(formatErrorDetail({ detail: 'denied' })).toBe('denied')
    expect(formatErrorDetail({ message: 'nope' })).toBe('nope')
    const msg = formatErrorDetail({ code: 'x', nested: true })
    expect(msg).not.toContain('[object Object]')
  })

  it('mapConnectionError redacts token-like strings', () => {
    expect(mapConnectionError('invalid ghp_abcdefghijklmnopqrstuvwxyz')).toMatch(/redacted|Invalid credentials/i)
  })

  it('safeLoginError strips HTML in production', () => {
    expect(
      safeLoginError('<!DOCTYPE html><html>boom</html>', { isProd: true })
    ).toMatch(/Login failed/i)
  })
})
