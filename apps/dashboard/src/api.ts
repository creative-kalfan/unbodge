import { z } from 'zod'

// Same-origin only. Development and preview proxy this prefix to loopback.
export const API_BASE = '/api/dashboard'
const nullable = z.string().nullable().optional()
const record = z.object({ id: z.string(), title: z.string(), repository_id: nullable,
  repository: nullable, file_path: nullable, created_at: nullable })
export const investigation = record.extend({ candidate_id: z.string(), issue_id: z.string(),
  fix_id: nullable, release_id: nullable, workflow_status: z.string() })
const decision = z.object({ id: z.string(), hypothesis_id: z.string().nullable(), outcome: z.enum(['ABSTAIN', 'PROPOSE_REMOVAL']),
  policy_mode: z.string(), rationale: z.string(), evidence_ids: z.array(z.string()), created_at: z.string().nullable() })
const proposal = z.object({ id: z.string(), decision_id: z.string(), title: z.string(), branch: z.string(), base: z.string().nullable(), body: z.string(), authorization_status: z.literal('UNVERIFIED') })
const integration = z.object({ name: z.string(), configuration: z.string(), authentication: z.literal('NOT_TESTED'),
  operation: z.enum(['NOT_TESTED', 'AVAILABLE', 'UNAVAILABLE']), note: z.string() })
export const snapshotSchema = z.object({ observed_at: z.string(), repositories: z.array(record), events: z.array(record), candidates: z.array(record),
  investigations: z.array(investigation), decisions: z.array(decision), proposals: z.array(proposal), truncated: z.boolean(), invalid_records: z.number(),
  health: z.object({ store: z.string(), cache: z.string(), authentication: z.enum(['BEARER_REQUIRED', 'LOCAL_DEV_READ_ONLY']), integrations: z.array(integration) }) })
export const detailSchema = z.object({ investigation, decisions: z.array(decision), proposals: z.array(proposal),
  observation: z.object({ scenario: z.literal('SYNTHETIC'), execution: z.enum(['REAL_DOCKER', 'NOT_EXECUTED']),
    provenance: z.enum(['CONTROLLED_FIXTURE', 'UNVERIFIED']), reasoning: z.enum(['NOT_REQUESTED', 'LIVE_NEBIUS', 'UNAVAILABLE']),
    completed_stages: z.array(z.string()), state: z.string(), transitions: z.array(z.object({ state: z.string(), at: z.string() })),
    advisory: z.object({ summary: z.string(), suspected_cause: z.string(), uncertainties: z.array(z.string()), verified: z.literal(false) }).nullable()
  }).nullable().optional(),
  evidence: z.array(z.object({ id: z.string(), evidence_type: z.string(), source: z.string(), claim: z.string(), hash: nullable,
    integrity: z.enum(['VALID', 'INVALID']), artifact_ref: nullable, experiment_id: nullable, timestamp: nullable })),
  runs: z.array(z.object({ id: z.string(), cell: z.enum(['A', 'B', 'C', 'D']), status: z.enum(['PASS', 'FAIL']), git_sha: z.string(), artifact_hash: nullable,
    duration_s: z.number(), exit_code: z.number(), receipt_status: z.literal('NOT_EXPOSED_PROCESS_LOCAL') })),
  regressions: z.array(z.object({ id: z.string(), status: z.enum(['PASS', 'FAIL']), passed: z.number(), failed: z.number(), git_sha: nullable, artifact_hash: nullable })),
  missing_evidence_ids: z.array(z.string()), authorization_status: z.literal('UNVERIFIED'), workflow_status: z.literal('UNAVAILABLE'), warnings: z.array(z.string()) })
export const readinessCheckSchema = z.object({
  name: z.string(),
  status: z.enum(['PASS', 'MISSING', 'UNSUPPORTED', 'UNVERIFIED']),
  explanation: z.string(),
})

export const readinessAssessmentSchema = z.object({
  repository: z.string(),
  owner: z.string(),
  name: z.string(),
  default_branch: z.string().nullable().optional(),
  accessible: z.boolean(),
  checks: z.array(readinessCheckSchema),
  can_connect: z.boolean(),
  proof_ready: z.boolean(),
  summary: z.string(),
})

export type ReadinessCheck = z.infer<typeof readinessCheckSchema>
export type ReadinessAssessment = z.infer<typeof readinessAssessmentSchema>

export type Snapshot = z.infer<typeof snapshotSchema>
export type Detail = z.infer<typeof detailSchema>
export type Investigation = z.infer<typeof investigation>

export class ApiError extends Error {
  constructor(message: string, public status = 0) { super(message) }
}

export async function request<T>(path: string, schema: z.ZodType<T>, token: string, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController()
  let timedOut = false
  const cancel = () => controller.abort()
  signal?.addEventListener('abort', cancel, { once: true })
  if (signal?.aborted) controller.abort()
  const timer = setTimeout(() => { timedOut = true; controller.abort() }, 10000)
  try {
    const response = await fetch(`${API_BASE}${path}`, { method: 'GET', credentials: 'omit', cache: 'no-store',
      headers: token ? { Authorization: `Bearer ${token}` } : {}, signal: controller.signal })
    if (!response.ok) {
      const messages: Record<number, string> = { 401: 'Operator authentication required. Open connection settings.', 403: 'Operator authentication rejected. Check your API token.',
        404: 'Record not found in this backend.', 422: 'The backend cannot display this record safely.', 429: 'Too many requests. Please wait before retrying.' }
      // Do not forward exception bodies, URLs, headers or stack traces into UI.
      throw new ApiError(messages[response.status] ?? 'Backend unavailable. Check the API connection and try again.', response.status)
    }
    const parsed = schema.safeParse(await response.json())
    if (!parsed.success) throw new ApiError('The backend returned an unsupported response. No data has been assumed valid.')
    return parsed.data
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError')
    throw new ApiError(timedOut ? 'The backend request timed out. Try again.' : 'Backend unavailable. Check the API connection and try again.')
  } finally {
    clearTimeout(timer); signal?.removeEventListener('abort', cancel)
  }
}

export async function saveRepository(fullName: string, token: string): Promise<{ id: string, full_name: string }> {
  const response = await fetch('/repositories', {
    method: 'POST',
    credentials: 'omit',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ full_name: fullName }),
  })
  if (!response.ok) {
    if (response.status === 401) throw new ApiError('Operator authentication required.', 401)
    if (response.status === 403) throw new ApiError('Operator token rejected.', 403)
    throw new ApiError(`Failed to save repository: HTTP ${response.status}`, response.status)
  }
  return response.json()
}

export async function approveDecision(decisionId: string, reviewer: string, comment: string, token: string): Promise<any> {
  const response = await fetch(`/decisions/${encodeURIComponent(decisionId)}/approve`, {
    method: 'POST',
    credentials: 'omit',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ reviewer, comment }),
  })
  if (!response.ok) {
    if (response.status === 401) throw new ApiError('Operator authentication required.', 401)
    if (response.status === 403) throw new ApiError('Operator token rejected.', 403)
    if (response.status === 422) throw new ApiError('Only PROPOSE_REMOVAL decisions can be approved; nothing is auto-merged.', 422)
    throw new ApiError(`Failed to record approval: HTTP ${response.status}`, response.status)
  }
  return response.json()
}
