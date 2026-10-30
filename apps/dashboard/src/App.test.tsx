import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { vi, test, expect } from 'vitest'
import { App } from './App'
import { snapshot } from './test/records'

function start(path = '/') { return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }
function respond(data = snapshot) { vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => data })) }

test('loads real counts then navigates with keyboard accessible links', async () => {
  respond(); start()
  expect(screen.getByRole('status')).toHaveTextContent('Loading')
  await screen.findByRole('heading', { name: 'Operational overview' })
  const user = userEvent.setup()
  await user.click(screen.getByRole('link', { name: 'Investigations' }))
  expect(await screen.findByRole('heading', { name: 'Investigations' })).toBeInTheDocument()
  expect(screen.getByText('No investigation records yet')).toBeInTheDocument()
  await user.tab()
  expect(document.activeElement?.tagName).not.toBe('BODY')
})

test('HTTP errors do not render secret-bearing server details and retry works', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ detail: 'password=SYNTHETIC_PRIVATE' }) })
    .mockResolvedValue({ ok: true, status: 200, json: async () => snapshot })
  vi.stubGlobal('fetch', fetcher); start()
  expect(await screen.findByRole('alert')).toHaveTextContent('unavailable')
  expect(document.body).not.toHaveTextContent('SYNTHETIC_PRIVATE')
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
  await screen.findByRole('heading', { name: 'Operational overview' })
})

test('unavailable integrations are never displayed as operational', async () => {
  respond(); start('/integrations')
  await screen.findByRole('heading', { name: 'Integrations & system health' })
  expect(screen.getAllByText('Not tested').length).toBeGreaterThan(0)
  expect(screen.getByText('MemoryStore')).toBeInTheDocument()
})

test('ABSTAIN stays distinct and stored proposals never become authorized', async () => {
  respond({ ...snapshot, decisions: [{ id: 'd', hypothesis_id: 'h', outcome: 'ABSTAIN', policy_mode: 'PROPOSE_ONLY', rationale: 'Missing proof', evidence_ids: [], created_at: '2026-10-27T00:00:00Z' }],
    proposals: [{ id: 'p', decision_id: 'd', title: 'Stored proposal', branch: 'test', base: 'main', body: '', authorization_status: 'UNVERIFIED' }] })
  start('/proposals')
  expect((await screen.findAllByText('Abstained')).length).toBeGreaterThan(0)
  expect(screen.getByText('Authorization unverified')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /create|approve|merge/i })).not.toBeInTheDocument()
})

test('missing evidence and missing workflow cannot produce successful proof', async () => {
  const detail = { investigation: { id: 'h', title: 'Fallback hypothesis', candidate_id: 'c', issue_id: 'i', workflow_status: 'UNAVAILABLE' },
    decisions: [], evidence: [], runs: [], regressions: [], proposals: [], missing_evidence_ids: ['missing'],
    authorization_status: 'UNVERIFIED', workflow_status: 'UNAVAILABLE', warnings: ['No persisted workflow state.'] }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string) => ({ ok: true, status: 200,
    json: async () => url.endsWith('/snapshot') ? snapshot : detail })))
  start('/investigations/h')
  await screen.findByRole('heading', { name: 'Fallback hypothesis' })
  expect(screen.getByText(/Missing evidence: missing/)).toBeInTheDocument()
  expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0)
  expect(screen.queryByText('Passed')).not.toBeInTheDocument()
})

test('unknown routes have a useful not found page', async () => {
  respond(); start('/unknown'); await screen.findByRole('heading', { name: 'Page not found' })
})

test('malformed responses fail closed without a fake success', async () => {
  respond({ status: 'ok' } as unknown as typeof snapshot); start()
  expect(await screen.findByRole('alert')).toHaveTextContent('unsupported response')
})

test('operator credentials stay in memory, outside storage and URLs', async () => {
  respond(); start(); await screen.findByRole('heading', { name: 'Operational overview' })
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Connection settings' }))
  await user.type(screen.getByLabelText('Operator API token'), 'synthetic-operator')
  await user.click(screen.getByRole('button', { name: 'Connect' }))
  await waitFor(() => expect(fetch).toHaveBeenLastCalledWith('/api/dashboard/snapshot', expect.objectContaining({ headers: { Authorization: 'Bearer synthetic-operator' } })))
  expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0)
  expect(document.body).not.toHaveTextContent('synthetic-operator')
})

test('search and decision filters do not fabricate records', async () => {
  respond({ ...snapshot, investigations: [{ id: 'h', title: 'Fallback hypothesis', candidate_id: 'c', issue_id: 'i', workflow_status: 'UNAVAILABLE' }] })
  start('/investigations')
  await screen.findByText('Fallback hypothesis')
  await userEvent.type(screen.getByRole('textbox', { name: 'Search investigations' }), 'unknown')
  expect(screen.getByText('No matching records')).toBeInTheDocument()
  await userEvent.clear(screen.getByRole('textbox', { name: 'Search investigations' }))
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Filter decisions' }), 'PROPOSE_REMOVAL')
  expect(screen.getByText('No matching records')).toBeInTheDocument()
})

test('long hostile text remains plain text and does not become HTML', async () => {
  const text = '<img src=x onerror=alert(1)>' + 'long-evidence-'.repeat(300)
  respond({ ...snapshot, decisions: [{ id: 'd', hypothesis_id: null, outcome: 'ABSTAIN', policy_mode: 'PROPOSE_ONLY', rationale: text, evidence_ids: [], created_at: '2026-10-27T00:00:00Z' }] })
  const { container } = start('/proposals')
  await screen.findByText(text)
  expect(container.querySelector('img')).toBeNull()
  expect(document.body).toHaveTextContent('Abstained')
})

test('opaque investigation IDs retain encoded slashes across route and API lookup', async () => {
  const detail = { investigation: { id: 'h:actual/backend', title: 'Encoded identity', candidate_id: 'c', issue_id: 'i', workflow_status: 'UNAVAILABLE' },
    decisions: [], evidence: [], runs: [], regressions: [], proposals: [], missing_evidence_ids: [], authorization_status: 'UNVERIFIED', workflow_status: 'UNAVAILABLE', warnings: [] }
  const fetcher = vi.fn().mockImplementation(async (url: string) => ({ ok: true, status: 200, json: async () => url.endsWith('/snapshot') ? snapshot : detail }))
  vi.stubGlobal('fetch', fetcher); start('/investigations/h%3Aactual%2Fbackend')
  await screen.findByRole('heading', { name: 'Encoded identity' })
  expect(fetcher).toHaveBeenLastCalledWith('/api/dashboard/investigations/h%3Aactual%2Fbackend', expect.anything())
})
