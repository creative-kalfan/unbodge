import { afterEach, expect, test, vi } from 'vitest'
import { readinessAssessmentSchema, request, snapshotSchema } from './api'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
test('request has an explicit timeout without forwarding errors', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn().mockImplementation((_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('secret=SYNTHETIC_PRIVATE'))))))
  const result = request('/snapshot', snapshotSchema, '').catch(error => error.message)
  await vi.advanceTimersByTimeAsync(10001)
  expect(await result).toContain('timed out')
  expect(await result).not.toContain('SYNTHETIC_PRIVATE')
})

test('caller cancellation does not become backend success', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation((_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('cancelled'))))))
  const controller = new AbortController()
  const result = request('/snapshot', snapshotSchema, '', controller.signal).catch(error => error.name)
  controller.abort()
  expect(await result).toBe('AbortError')
})

test('authentication rejection uses a fixed safe message', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }))
  await expect(request('/snapshot', snapshotSchema, '')).rejects.toThrow('authentication required')
})

test('readiness assessment schema parses valid assessment', () => {
  const valid = {
    repository: 'psf/requests',
    owner: 'psf',
    name: 'requests',
    default_branch: 'main',
    accessible: true,
    checks: [
      { name: 'Repository accessible', status: 'PASS', explanation: 'Reachable' },
      { name: 'Docker execution available', status: 'PASS', explanation: 'Available' },
    ],
    can_connect: true,
    proof_ready: false,
    summary: 'Ready for connection',
  }
  const parsed = readinessAssessmentSchema.safeParse(valid)
  expect(parsed.success).toBe(true)
})
