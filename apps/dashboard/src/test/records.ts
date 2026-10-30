// Test-only records. The shipped app has no fixtures, demo fallback or mock mode.
import type { Snapshot } from '../api'
export const snapshot: Snapshot = {
  observed_at: '2026-10-27T00:00:00Z', repositories: [], events: [], candidates: [], investigations: [], decisions: [], proposals: [], truncated: false, invalid_records: 0,
  health: { store: 'MemoryStore', cache: 'MemoryCache', authentication: 'LOCAL_DEV_READ_ONLY', integrations: [
    { name: 'GitHub', configuration: 'NOT_CONFIGURED', authentication: 'NOT_TESTED', operation: 'NOT_TESTED', note: 'No network probe performed.' },
  ] },
}
