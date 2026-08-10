import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import UnifiedApprovalsInbox from '../components/approvals/UnifiedApprovalsInbox'

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  }
}

const LOW_RISK_ITEM = {
  id: 'access:req-1',
  source: 'access',
  title: 'Access: newhire → prod-db',
  description: 'Grant read access',
  risk: 'low',
  grounding: null,
  requester: 'newhire',
  created_at: new Date().toISOString(),
  age_seconds: 120,
  sla_breached: false,
  needs_typed_confirmation: false,
  needs_second_approver: false,
  approvers: [],
  approvals_required: null,
  service: 'prod-db',
  detail: {},
}

const TYPED_CONFIRM_ITEM = {
  id: 'agent:run-1',
  source: 'agent',
  title: 'terraform.apply_plan',
  description: 'Destroy 3 resources',
  risk: 'high',
  grounding: 'live',
  requester: 'deployer',
  created_at: new Date().toISOString(),
  age_seconds: 60,
  sla_breached: false,
  needs_typed_confirmation: true,
  needs_second_approver: false,
  approvers: [],
  approvals_required: null,
  service: null,
  detail: { commands: ['terraform apply'] },
}

let authFetchMock

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ authFetch: authFetchMock }),
}))

vi.mock('../components/ToastNotification', () => ({
  useToast: () => ({ toast: { success: vi.fn(), error: vi.fn() } }),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function mockInboxFetch(items) {
  authFetchMock = vi.fn(async (url, opts = {}) => {
    const method = (opts.method || 'GET').toUpperCase()
    if (String(url).startsWith('/api/approvals/inbox') && method === 'GET') {
      return jsonResponse(200, { items, total: items.length, page: 1, page_size: 25 })
    }
    if (String(url).includes('/approve') && method === 'POST') {
      return jsonResponse(200, { ok: true })
    }
    if (String(url).includes('/bulk-approve') && method === 'POST') {
      return jsonResponse(200, { results: items.filter((i) => i.risk === 'low').map((i) => ({ id: i.id, ok: true })) })
    }
    return jsonResponse(200, {})
  })
  return authFetchMock
}

describe('UnifiedApprovalsInbox', () => {
  it('renders items from the inbox endpoint', async () => {
    mockInboxFetch([LOW_RISK_ITEM, TYPED_CONFIRM_ITEM])
    render(<UnifiedApprovalsInbox />)
    await waitFor(() => {
      expect(screen.getByText('Access: newhire → prod-db')).toBeTruthy()
      expect(screen.getByText('terraform.apply_plan')).toBeTruthy()
    })
  })

  it('approves the focused item on "a" and moves focus with j/k', async () => {
    const fetchMock = mockInboxFetch([LOW_RISK_ITEM, TYPED_CONFIRM_ITEM])
    render(<UnifiedApprovalsInbox />)
    await waitFor(() => expect(screen.getByText('Access: newhire → prod-db')).toBeTruthy())

    fireEvent.keyDown(window, { key: 'j' }) // move focus to the second item
    fireEvent.keyDown(window, { key: 'a' }) // approve focused (typed-confirm) item

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/approvals/agent%3Arun-1/approve',
        expect.objectContaining({ method: 'POST' })
      )
    })
  })

  it('disables bulk-select for items needing typed confirmation, enables for low risk', async () => {
    mockInboxFetch([LOW_RISK_ITEM, TYPED_CONFIRM_ITEM])
    render(<UnifiedApprovalsInbox />)
    await waitFor(() => expect(screen.getByText('Access: newhire → prod-db')).toBeTruthy())

    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes).toHaveLength(2)
    const [lowRiskBox, typedConfirmBox] = checkboxes
    expect(lowRiskBox).not.toBeDisabled()
    expect(typedConfirmBox).toBeDisabled()
  })

  it('bulk-approves only the selected low-risk items after confirmation', async () => {
    const fetchMock = mockInboxFetch([LOW_RISK_ITEM, TYPED_CONFIRM_ITEM])
    render(<UnifiedApprovalsInbox />)
    await waitFor(() => expect(screen.getByText('Access: newhire → prod-db')).toBeTruthy())

    const [lowRiskBox] = screen.getAllByRole('checkbox')
    fireEvent.click(lowRiskBox)

    const approveSelected = await screen.findByText(/Approve 1 selected/i)
    fireEvent.click(approveSelected)

    const confirmButton = await screen.findByText('Approve all')
    fireEvent.click(confirmButton)

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/approvals/bulk-approve',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ ids: ['access:req-1'] }),
        })
      )
    })
  })
})
