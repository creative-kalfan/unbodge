import { createContext, useContext, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Link, NavLink, Route, Routes, useLocation, useParams } from 'react-router'
import * as Dialog from '@radix-ui/react-dialog'
import {
  Activity, ArrowDownLeft, ArrowUpRight, Braces, Check, ChevronRight, CircleDot,
  FileCheck2, FileCode2, Files, FlaskConical, GitBranch, GitFork, Layers3,
  LayoutDashboard, LockKeyhole, Play, RefreshCw, Search, Settings2, ShieldAlert,
  ShieldCheck, ShieldQuestion, Sparkles, Unplug, X
} from 'lucide-react'
import {
  ApiError, detailSchema, readinessAssessmentSchema, request,
  saveRepository, snapshotSchema
} from './api'
import type { Detail, Investigation, ReadinessAssessment, Snapshot } from './api'

const ConnectionContext = createContext({ token: '', revision: 0 })

const nav = [
  ['/', 'Overview', LayoutDashboard],
  ['/repositories', 'Repositories', GitFork],
  ['/investigations', 'Investigations', Search],
  ['/proof', 'Proof Explorer', Layers3],
  ['/evidence', 'Evidence Ledger', FileCheck2],
  ['/proposals', 'Proposal Review', GitBranch],
  ['/integrations', 'Integrations', Unplug],
  ['/security', 'Security & Audit', ShieldCheck],
] as const

function Badge({ value }: { value: string }) {
  const labels: Record<string, string> = {
    ABSTAIN: 'Abstained',
    PROPOSE_REMOVAL: 'Removal proposed',
    UNAVAILABLE: 'Unavailable',
    UNVERIFIED: 'Authorization unverified',
    VALID: 'Integrity valid',
    INVALID: 'Integrity invalid',
    PASS: 'Recorded pass',
    FAIL: 'Recorded fail',
    MISSING: 'Missing requirement',
    UNSUPPORTED: 'Unsupported format',
    NOT_TESTED: 'Not tested',
    NOT_CONFIGURED: 'Not configured',
    CONFIGURED: 'Configured',
    AVAILABLE: 'Available',
    NOT_ATTACHED: 'Not attached',
    ATTACHED: 'Attached',
  }
  return (
    <span className={`badge badge-${value.toLowerCase()}`}>
      <span aria-hidden="true" />
      {labels[value] ?? value}
    </span>
  )
}

function Empty({ title, children, icon: Icon = Files }: { title: string, children: ReactNode, icon?: typeof Files }) {
  return (
    <div className="empty">
      <div className="empty-icon"><Icon size={25} strokeWidth={1.3} /></div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  )
}

function ErrorPanel({ error, retry }: { error: string, retry: () => void }) {
  return (
    <div className="error-panel" role="alert">
      <ShieldQuestion size={24} />
      <div>
        <h2>Couldn’t load backend data</h2>
        <p>{error}</p>
        <button className="button" onClick={retry}>Try again</button>
      </div>
    </div>
  )
}

function PageTitle({ eyebrow, title, description, extra }: { eyebrow: string, title: string, description: string, extra?: ReactNode }) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="description">{description}</p>
      </div>
      {extra}
    </div>
  )
}

function IntegrityNote() {
  return (
    <div className="notice">
      <ShieldQuestion size={17} />
      <span>Stored observations. Live proof authorization is unavailable in this read-only interface. The AI never authorizes its own conclusions.</span>
    </div>
  )
}

function DecisionList({ data }: { data: Snapshot['decisions'] }) {
  return data.length ? (
    <div className="record-list">
      {data.map(d => (
        <div className="record" key={d.id}>
          <div className="record-title">
            <Badge value={d.outcome} />
            <code>{d.id}</code>
          </div>
          <p>{d.rationale}</p>
          <small>{d.policy_mode} · {d.evidence_ids.length} evidence references</small>
        </div>
      ))}
    </div>
  ) : (
    <Empty title="No policy decisions recorded" icon={ShieldCheck}>
      Decisions appear here only when they exist in this API’s Store.
    </Empty>
  )
}

function InvestigationTable({ data, decisions, proof = false }: { data: Investigation[], decisions: Snapshot['decisions'], proof?: boolean }) {
  if (!data.length) {
    return (
      <Empty title="No investigation records yet" icon={Search}>
        The API has no stored causal hypotheses to browse. Running a CLI demo does not automatically populate this Store.
      </Empty>
    )
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Investigation</th>
            <th>Repository / candidate</th>
            <th>Recorded decisions</th>
            <th>Workflow</th>
            <th><span className="sr-only">Open record</span></th>
          </tr>
        </thead>
        <tbody>
          {data.map(h => (
            <tr key={h.id}>
              <td>
                <Link className="row-link" to={`/${proof ? 'proof' : 'investigations'}/${encodeURIComponent(h.id)}`}>{h.title}</Link>
                <code className="subline">{h.id}</code>
              </td>
              <td>
                {h.repository ?? h.repository_id ?? 'Repository unavailable'}
                <code className="subline">{h.file_path ?? h.candidate_id}</code>
              </td>
              <td>
                <div className="badge-stack">
                  {decisions.filter(d => d.hypothesis_id === h.id).map(d => (
                    <Badge key={d.id} value={d.outcome} />
                  ))}
                  {!decisions.some(d => d.hypothesis_id === h.id) && <span className="muted">Not recorded</span>}
                </div>
              </td>
              <td><Badge value={h.workflow_status} /></td>
              <td>
                <Link className="icon-link" aria-label={`Open ${h.id}`} to={`/${proof ? 'proof' : 'investigations'}/${encodeURIComponent(h.id)}`}>
                  <ArrowUpRight size={17} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// Phase 2: Masterstroke Feature — Repository Connection Wizard
function RepositoryConnectionWizard({ onSaved }: { onSaved?: () => void }) {
  const { token } = useContext(ConnectionContext)
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1)
  const [urlError, setUrlError] = useState('')
  const [owner, setOwner] = useState('')
  const [repo, setRepo] = useState('')
  const [loading, setLoading] = useState(false)
  const [assessment, setAssessment] = useState<ReadinessAssessment | null>(null)
  const [assessError, setAssessError] = useState('')
  const [saveSuccess, setSaveSuccess] = useState(false)

  function reset() {
    setUrl('')
    setStep(1)
    setUrlError('')
    setOwner('')
    setRepo('')
    setAssessment(null)
    setAssessError('')
    setSaveSuccess(false)
  }

  function handleUrlChange(val: string) {
    setUrl(val)
    setUrlError('')
  }

  function validateUrl() {
    const trimmed = url.trim()
    const match = trimmed.match(/^https?:\/\/github\.com\/([a-zA-Z0-9_.-]+)\/([a-zA-Z0-9_.-]+?)(?:\.git|\/)?$/)
    if (!match) {
      setUrlError('Please enter a valid GitHub repository URL (e.g. https://github.com/psf/requests). Non-GitHub hosts and arbitrary URLs are rejected.')
      return false
    }
    const o = match[1]
    const r = match[2]
    setOwner(o)
    setRepo(r)
    return { owner: o, repo: r }
  }

  async function inspectRepository(parsedOwner?: string, parsedRepo?: string) {
    const o = parsedOwner || owner
    const r = parsedRepo || repo
    if (!o || !r) return
    setLoading(true)
    setAssessError('')
    try {
      const res = await request(`/readiness/${encodeURIComponent(o)}/${encodeURIComponent(r)}`, readinessAssessmentSchema, token)
      setAssessment(res)
      setStep(4)
    } catch (e) {
      setAssessError(e instanceof ApiError ? e.message : 'Failed to inspect repository.')
    } finally {
      setLoading(false)
    }
  }

  function proceedToInspect(e: FormEvent) {
    e.preventDefault()
    const parsed = validateUrl()
    if (!parsed) return
    setStep(3)
    inspectRepository(parsed.owner, parsed.repo)
  }

  async function handleSave() {
    if (!owner || !repo) return
    setLoading(true)
    try {
      await saveRepository(`${owner}/${repo}`, token)
      setSaveSuccess(true)
      onSaved?.()
    } catch (e) {
      setAssessError(e instanceof ApiError ? e.message : 'Failed to save repository.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={next => { setOpen(next); if (!next) reset() }}>
      <Dialog.Trigger asChild>
        <button className="button primary" aria-label="Connect Repository">
          <GitFork size={15} /> Connect Repository
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content" style={{ maxWidth: '640px' }}>
          <Dialog.Title>Connect Repository & Proof Assessment</Dialog.Title>
          <Dialog.Description>
            Safe, read-only repository inspection. Evaluates single-package pin prerequisites and provenance readiness before onboarding.
          </Dialog.Description>

          {step === 1 && (
            <form onSubmit={proceedToInspect}>
              <label className="field-label" htmlFor="repo-url">GitHub Repository URL</label>
              <input
                id="repo-url"
                type="url"
                placeholder="https://github.com/psf/requests"
                value={url}
                onChange={e => handleUrlChange(e.target.value)}
                autoFocus
              />
              <p className="muted text-sm">
                Example targets: <code>https://github.com/psf/requests</code> or <code>https://github.com/pypa/pip</code>
              </p>
              {urlError && <div className="notice danger" style={{ marginTop: '10px' }}>{urlError}</div>}
              <div className="wizard-actions">
                <span className="muted text-sm">Step 1 of 4: URL Validation</span>
                <button className="button primary" type="submit" disabled={!url.trim()}>
                  Inspect Readiness <ArrowUpRight size={14} />
                </button>
              </div>
            </form>
          )}

          {step === 3 && (
            <div className="loading" style={{ minHeight: '180px' }}>
              <CircleDot size={20} />
              <span>Inspecting {owner}/{repo} via read-only safe metadata checks…</span>
            </div>
          )}

          {step === 4 && assessment && (
            <div>
              <div className="record" style={{ background: '#11141b', borderRadius: '6px', marginBottom: '14px' }}>
                <div className="record-title">
                  <strong>{assessment.repository}</strong>
                  <Badge value={assessment.accessible ? 'PASS' : 'UNVERIFIED'} />
                </div>
                <small>Default branch: <code>{assessment.default_branch ?? 'Unspecified'}</code> · Live provenance unverified</small>
              </div>

              <div className="notice" style={{ marginBottom: '12px' }}>
                <ShieldAlert size={16} />
                <span>{assessment.summary}</span>
              </div>

              <p className="field-label">Proof Readiness Assessment (9 Verification Gates)</p>
              <div className="checklist">
                {assessment.checks.map(check => (
                  <div className="checklist-item" key={check.name}>
                    <div>
                      <span className="checklist-item-title">{check.name}</span>
                      <p className="checklist-item-expl">{check.explanation}</p>
                    </div>
                    <Badge value={check.status} />
                  </div>
                ))}
              </div>

              {assessError && <div className="notice danger">{assessError}</div>}
              {saveSuccess ? (
                <div className="notice" style={{ borderColor: '#314e44', color: '#a5d2c1', background: '#1b2926' }}>
                  <Check size={16} />
                  <span>Repository <code>{assessment.repository}</code> saved to workspace store successfully.</span>
                </div>
              ) : (
                <div className="wizard-actions">
                  <button className="button" type="button" onClick={() => setStep(1)} disabled={loading}>
                    Back
                  </button>
                  <button className="button primary" type="button" onClick={handleSave} disabled={loading}>
                    {loading ? 'Saving…' : 'Save Repository to Workspace'}
                  </button>
                </div>
              )}
            </div>
          )}

          <Dialog.Close className="dialog-close icon-button" aria-label="Close dialog">
            <X size={18} />
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function Overview({ data, onConnectRepo }: { data: Snapshot, onConnectRepo?: () => void }) {
  const abstentions = data.decisions.filter(d => d.outcome === 'ABSTAIN').length
  const proposed = data.decisions.filter(d => d.outcome === 'PROPOSE_REMOVAL').length

  return (
    <>
      <PageTitle
        eyebrow="Workspace / Overview"
        title="Operational overview"
        description="Evidence before action. Follow the evidence. Understand every proposed removal."
        extra={
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <RepositoryConnectionWizard onSaved={onConnectRepo} />
            <Link className="button" to="/investigations">
              <Play size={14} /> Run Demonstration
            </Link>
          </div>
        }
      />
      <div className="metrics">
        {[
          [data.investigations.length, 'Total investigations', Search, 'Stored causal hypotheses'],
          [proposed, 'Removal proposals', GitBranch, 'Evidence-proven removals'],
          [abstentions, 'Abstained decisions', ShieldQuestion, 'Fail-closed safety gate declined'],
          [data.health.integrations.filter(i => i.operation === 'AVAILABLE' || i.configuration === 'CONFIGURED').length, 'Connected integrations', Unplug, 'Live verified adapters'],
        ].map(([count, label, Icon, note]) => {
          const Glyph = Icon as typeof Search
          return (
            <div className="metric" key={String(label)}>
              <div className="metric-top">
                <span>{String(label)}</span>
                <Glyph size={17} />
              </div>
              <strong>{String(count)}</strong>
              <small>{String(note)}</small>
            </div>
          )
        })}
      </div>
      <IntegrityNote />
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Recent Investigations</h2>
            <p>Exact links to recorded hypotheses, candidate workarounds, and deterministic decisions.</p>
          </div>
          <Link className="text-link" to="/investigations">View all <ArrowUpRight size={15} /></Link>
        </div>
        <InvestigationTable data={data.investigations.slice(0, 5)} decisions={data.decisions} />
      </section>
      <div className="two-column">
        <section className="panel">
          <div className="panel-heading">
            <h2>Recorded policy decisions</h2>
            <ShieldCheck size={17} />
          </div>
          <DecisionList data={data.decisions.slice(-4).reverse()} />
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>Upstream activity</h2>
            <Activity size={17} />
          </div>
          {data.events.length ? (
            <div className="record-list">
              {data.events.slice(-5).reverse().map(e => (
                <div className="record" key={e.id}>
                  <div className="record-title">
                    <CircleDot size={15} />
                    <strong>{e.title}</strong>
                  </div>
                  <code>{e.repository_id ?? 'Repository unavailable'}</code>
                  <small>{e.created_at ? new Date(e.created_at).toLocaleString() : 'Timestamp unavailable'}</small>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="No upstream events recorded" icon={Activity}>
              Webhook receipt records appear here. A receipt alone does not mean an investigation has run.
            </Empty>
          )}
        </section>
      </div>
      <div className="footnote">
        <LockKeyhole size={14} /> Snapshot from this API instance · counts are bounded to 200 records per collection · active workflow counts unavailable
      </div>
    </>
  )
}

function RepositoriesView({ data, onRefresh }: { data: Snapshot, onRefresh?: () => void }) {
  return (
    <>
      <PageTitle
        eyebrow="Workspace / Repositories"
        title="Repositories"
        description="Inspect registered GitHub repositories and their proof readiness status."
        extra={<RepositoryConnectionWizard onSaved={onRefresh} />}
      />
      <IntegrityNote />
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Monitored repositories</h2>
            <p>Registered repositories subject to dependency workaround scans and evidence checks.</p>
          </div>
          <span className="quiet-label">{data.repositories.length} recorded</span>
        </div>
        {data.repositories.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Repository Name</th>
                  <th>Identifier</th>
                  <th>Linked Candidates</th>
                  <th>Proof Readiness</th>
                </tr>
              </thead>
              <tbody>
                {data.repositories.map(r => {
                  const candidateCount = data.candidates.filter(c => c.repository_id === r.id).length
                  return (
                    <tr key={r.id}>
                      <td>
                        <strong>{r.title}</strong>
                        <code className="subline">{r.id}</code>
                      </td>
                      <td><code>{r.id}</code></td>
                      <td>{candidateCount} workaround candidate(s)</td>
                      <td>
                        <Badge value="UNVERIFIED" />
                        <span className="muted text-sm" style={{ display: 'block', marginTop: '4px' }}>
                          Live GitHub provenance unverified
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No repositories connected" icon={GitFork}>
            Connect a GitHub repository using the wizard above to begin proof readiness evaluation.
          </Empty>
        )}
      </section>
    </>
  )
}

function Investigations({ data, proof = false }: { data: Snapshot, proof?: boolean }) {
  const [query, setQuery] = useState('')
  const [outcome, setOutcome] = useState('all')
  const filtered = data.investigations.filter(h =>
    `${h.title} ${h.id} ${h.repository ?? ''} ${h.file_path ?? ''}`.toLowerCase().includes(query.toLowerCase()) &&
    (outcome === 'all' || data.decisions.some(d => d.hypothesis_id === h.id && d.outcome === outcome))
  )
  return (
    <>
      <PageTitle
        eyebrow={proof ? 'Workspace / Evidence' : 'Workspace / Investigations'}
        title={proof ? 'Proof Explorer' : 'Investigations'}
        description={proof ? 'Inspect recorded evidence, 4-cell matrices, and cryptographic receipts without granting authority.' : 'Browse stored causal hypotheses. Workflow execution stays with the backend.'}
      />
      <IntegrityNote />
      <section className="panel">
        <div className="filter-bar">
          <label className="search-field">
            <Search size={17} />
            <span className="sr-only">Search investigations</span>
            <input placeholder="Search records, repositories, files…" value={query} onChange={e => setQuery(e.target.value)} />
          </label>
          <label className="select-field">
            <span className="sr-only">Filter decisions</span>
            <select value={outcome} onChange={e => setOutcome(e.target.value)}>
              <option value="all">All decisions</option>
              <option value="ABSTAIN">Abstained</option>
              <option value="PROPOSE_REMOVAL">Removal proposed</option>
            </select>
          </label>
          <span className="muted text-sm">{filtered.length} records</span>
        </div>
        {data.investigations.length > 0 && filtered.length === 0 ? (
          <Empty title="No matching records">Change your search or decision filter.</Empty>
        ) : (
          <InvestigationTable data={filtered} decisions={data.decisions} proof={proof} />
        )}
      </section>
      <div className="two-column">
        <section className="panel">
          <div className="panel-heading">
            <h2>Watched repositories</h2>
            <Braces size={17} />
          </div>
          {data.repositories.length ? (
            <div className="record-list">
              {data.repositories.map(r => (
                <div className="record" key={r.id}>
                  <strong>{r.title}</strong>
                  <code className="subline">{r.id}</code>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="No repositories recorded">Connect a repository using the top wizard to begin monitoring.</Empty>
          )}
        </section>
        <section className="panel">
          <div className="panel-heading">
            <h2>Workaround candidates</h2>
            <FileCode2 size={17} />
          </div>
          {data.candidates.length ? (
            <div className="record-list">
              {data.candidates.map(c => (
                <div className="record" key={c.id}>
                  <strong>{c.title}</strong>
                  <code className="subline">{c.file_path}</code>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="No candidates recorded">A candidate is not an investigation or a validated removal.</Empty>
          )}
        </section>
      </div>
    </>
  )
}

function ProofPanels({ detail }: { detail: Detail }) {
  const cells = [
    ['A', 'Old dependency', 'Workaround present', 'Expected: PASS'],
    ['B', 'Old dependency', 'Workaround removed', 'Expected: FAIL'],
    ['C', 'New dependency', 'Workaround present', 'Expected: PASS'],
    ['D', 'New dependency', 'Workaround removed', 'Expected: PASS'],
  ]
  return (
    <>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Counterfactual 4-Cell Matrix</h2>
            <p>Mathematical proof of obsolescence. Only exact experiment IDs referenced by verified evidence are displayed.</p>
          </div>
          <FlaskConical size={18} />
        </div>
        <div className="matrix">
          {cells.map(([cell, dep, workaround, expected]) => {
            const runs = detail.runs.filter(r => r.cell === cell)
            return (
              <div className="matrix-cell" key={cell}>
                <div className="matrix-label">
                  Cell {cell}
                  <span>{dep}</span>
                </div>
                <p>{workaround}</p>
                <small className="muted">{expected}</small>
                {!runs.length && <Badge value="UNAVAILABLE" />}
                {runs.map(r => (
                  <div key={r.id} className="run-details">
                    <Badge value={r.status} />
                    <code>{r.id}</code>
                    <small>Exit {r.exit_code} · {r.duration_s}s</small>
                    <small>Revision</small>
                    <code>{r.git_sha}</code>
                    <small>Input artifact hash</small>
                    <code>{r.artifact_hash ?? 'Unavailable'}</code>
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Evidence ledger</h2>
          <span className="quiet-label">Cryptographic SHA-256 checks</span>
        </div>
        {detail.evidence.length ? (
          <div className="evidence-grid">
            {detail.evidence.map(e => (
              <article className="evidence-card" key={e.id}>
                <div className="record-title">
                  <span className="eyebrow">{e.evidence_type.replaceAll('_', ' ')}</span>
                  <Badge value={e.integrity} />
                </div>
                <h3>{e.claim}</h3>
                <dl>
                  <dt>Identity</dt>
                  <dd><code>{e.id}</code></dd>
                  <dt>Source</dt>
                  <dd>{e.source}</dd>
                  <dt>SHA-256</dt>
                  <dd><code>{e.hash ?? 'Unavailable'}</code></dd>
                  <dt>Artifact</dt>
                  <dd><code>{e.artifact_ref ?? 'Unavailable'}</code></dd>
                  <dt>Experiment</dt>
                  <dd><code>{e.experiment_id ?? 'Not applicable'}</code></dd>
                  <dt>Recorded</dt>
                  <dd>{e.timestamp ?? 'Unavailable'}</dd>
                </dl>
              </article>
            ))}
          </div>
        ) : (
          <Empty title="No linked evidence available" icon={Layers3}>
            Missing records cannot establish a successful proof. No unrelated experiments are substituted.
          </Empty>
        )}
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Regression observations</h2>
          <Check size={17} />
        </div>
        {detail.regressions.length ? (
          <div className="record-list">
            {detail.regressions.map(r => (
              <div className="record" key={r.id}>
                <Badge value={r.status} />
                <p>{r.passed} passed · {r.failed} failed</p>
                <code>{r.id}</code>
                <code className="subline">Revision: {r.git_sha ?? 'Unavailable'}</code>
                <code className="subline">Input artifact: {r.artifact_hash ?? 'Unavailable'}</code>
              </div>
            ))}
          </div>
        ) : (
          <Empty title="Regression record unavailable">
            No exact, integrity-checked regression record is linked to this investigation.
          </Empty>
        )}
      </section>
      <div className="notice">
        <LockKeyhole size={17} />
        <span>Execution receipts are process-local. They are not exposed or revalidated here and cannot be assumed to survive a restart.</span>
      </div>
    </>
  )
}

function InvestigationDetail({ proofOnly = false }: { proofOnly?: boolean }) {
  const { id } = useParams()
  const { token, revision } = useContext(ConnectionContext)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setDetail(null)
    setError('')
    request(`/investigations/${encodeURIComponent(id ?? '')}`, detailSchema, token, controller.signal)
      .then(result => { if (!controller.signal.aborted) setDetail(result) })
      .catch(e => { if (!controller.signal.aborted) setError(e instanceof ApiError ? e.message : 'Record unavailable.') })
    return () => controller.abort()
  }, [id, token, revision, retry])

  if (error) return <ErrorPanel error={error} retry={() => setRetry(n => n + 1)} />
  if (!detail) return <div role="status" className="loading">Loading investigation record…</div>

  const h = detail.investigation
  return (
    <>
      <Link className="back-link" to={proofOnly ? '/proof' : '/investigations'}>
        <ArrowDownLeft size={16} />All {proofOnly ? 'proof records' : 'investigations'}
      </Link>
      <PageTitle
        eyebrow={`${proofOnly ? 'Proof Explorer' : 'Investigation'} / ${h.id}`}
        title={h.title}
        description={h.repository ?? h.repository_id ?? 'Repository linkage unavailable'}
      />
      <IntegrityNote />

      <div className="panel metadata">
        <div><small>Workaround file</small><code>{h.file_path ?? h.candidate_id}</code></div>
        <div><small>Upstream issue</small><code>{h.issue_id}</code></div>
        <div><small>Fix commit</small><code>{h.fix_id ?? 'Unavailable'}</code></div>
        <div><small>Release tag</small><code>{h.release_id ?? 'Unavailable'}</code></div>
      </div>

      {detail.missing_evidence_ids.length > 0 && (
        <div className="notice danger">Missing evidence: {detail.missing_evidence_ids.join(', ')}</div>
      )}

      {detail.observation && (
        <div className="notice">
          <ShieldQuestion size={17} />
          <span>
            {detail.observation.scenario === 'SYNTHETIC' ? 'SYNTHETIC DEMONSTRATION' : 'REAL INVESTIGATION'} · Execution: {detail.observation.execution === 'REAL_DOCKER' ? 'REAL CONTAINER EXECUTION' : 'NOT EXECUTED'} · Provenance: {detail.observation.provenance === 'CONTROLLED_FIXTURE' ? 'CONTROLLED FIXTURE PROVENANCE' : 'LIVE GITHUB PROVENANCE UNVERIFIED'} · Reasoning: {detail.observation.reasoning}
          </span>
        </div>
      )}

      {detail.observation?.advisory && (
        <section className="panel">
          <div className="panel-heading">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Sparkles size={18} style={{ color: '#b7c4ff' }} />
              <h2>NVIDIA Nemotron Advisory Reasoning</h2>
            </div>
            <Badge value="UNVERIFIED" />
          </div>
          <div className="record">
            <p style={{ fontWeight: 500, color: '#e4e7ee' }}>{detail.observation.advisory.summary}</p>
            <p style={{ color: '#a3b2ca', marginTop: '8px' }}><strong>Suspected Root Cause:</strong> {detail.observation.advisory.suspected_cause}</p>
            <p className="field-label" style={{ marginTop: '12px' }}>Model Identified Uncertainties:</p>
            <ul style={{ paddingLeft: '20px', color: '#9199a9', fontSize: '11px', lineHeight: '1.7' }}>
              {detail.observation.advisory.uncertainties.map((u, i) => (
                <li key={i}>{u}</li>
              ))}
            </ul>
            <div className="notice" style={{ marginTop: '14px', borderColor: '#4e4231' }}>
              <LockKeyhole size={15} />
              <span>Nemotron is advisory only. Model output cannot authorize removal or verify proof.</span>
            </div>
          </div>
        </section>
      )}

      {!proofOnly && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Investigation Workflow Timeline</h2>
              <p>{detail.observation ? 'Chronological stage transitions from ingest to deterministic decision.' : 'No persisted workflow stages or timestamps are available through the Store contract.'}</p>
            </div>
            <Badge value={detail.observation?.state ?? 'UNAVAILABLE'} />
          </div>
          {detail.observation ? (
            <>
              <ol className="timeline">
                {detail.observation.transitions.map((t, i) => (
                  <li key={i}>
                    <span className="timeline-dot" />
                    <span>Stage {i + 1}: {t.state}</span>
                    <span className="muted">{new Date(t.at).toLocaleTimeString()}</span>
                  </li>
                ))}
              </ol>
              <p className="record" style={{ color: '#8f9db5', fontSize: '11px' }}>
                Pipeline Sequence: {detail.observation.completed_stages.join(' → ')}.
              </p>
            </>
          ) : (
            <Empty title="Timeline unavailable">No workflow transitions were recorded for this investigation.</Empty>
          )}
        </section>
      )}

      <section className="panel">
        <div className="panel-heading">
          <h2>Recorded policy decisions & security explanation</h2>
        </div>
        <DecisionList data={detail.decisions} />
      </section>

      <ProofPanels detail={detail} />

      <section className="panel">
        <div className="panel-heading">
          <h2>Uncertainties & system boundaries</h2>
        </div>
        <ul className="warnings">
          {detail.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      </section>
    </>
  )
}

function GlobalEvidenceLedger({ data }: { data: Snapshot }) {
  const [filter, setFilter] = useState('')
  const allDecisions = data.decisions
  return (
    <>
      <PageTitle
        eyebrow="Workspace / Evidence"
        title="Evidence Ledger"
        description="Global verification ledger. Immutable SHA-256 bound artifacts and execution citations across the system."
      />
      <IntegrityNote />
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Verified evidence items</h2>
            <p>Every decision must be backed by cryptographically valid, untampered evidence records.</p>
          </div>
          <span className="quiet-label">{allDecisions.reduce((acc, d) => acc + d.evidence_ids.length, 0)} linked citations</span>
        </div>
        <div className="filter-bar">
          <label className="search-field">
            <Search size={17} />
            <input placeholder="Search evidence IDs or decision references…" value={filter} onChange={e => setFilter(e.target.value)} />
          </label>
        </div>
        {allDecisions.length ? (
          <div className="record-list">
            {allDecisions.flatMap(d => d.evidence_ids.map(eid => ({ decision: d, evidenceId: eid })))
              .filter(item => item.evidenceId.toLowerCase().includes(filter.toLowerCase()) || item.decision.id.toLowerCase().includes(filter.toLowerCase()))
              .map(({ decision, evidenceId }) => (
                <div className="record" key={`${decision.id}-${evidenceId}`}>
                  <div className="record-title">
                    <code>{evidenceId}</code>
                    <Badge value={decision.outcome} />
                  </div>
                  <small>Referenced by Decision <code>{decision.id}</code> ({decision.policy_mode})</small>
                  <p>{decision.rationale}</p>
                </div>
              ))}
          </div>
        ) : (
          <Empty title="No evidence items found" icon={FileCheck2}>
            Evidence items are populated as counterfactual runs and provenance checks execute.
          </Empty>
        )}
      </section>
    </>
  )
}

function Proposals({ data }: { data: Snapshot }) {
  return (
    <>
      <PageTitle
        eyebrow="Workspace / Review"
        title="Proposal Review"
        description="Inspect stored proposal artifacts. The system is PROPOSE_ONLY. Merging stays with humans."
      />
      <IntegrityNote />
      <section className="panel">
        <div className="panel-heading">
          <h2>Stored proposals</h2>
          <span className="quiet-label">PROPOSE_ONLY invariant</span>
        </div>
        {data.proposals.length ? (
          <div className="proposal-list">
            {data.proposals.map(p => {
              const d = data.decisions.find(dec => dec.id === p.decision_id)
              return (
                <details className="proposal" key={p.id}>
                  <summary>
                    <GitBranch size={20} />
                    <div>
                      <strong>{p.title}</strong>
                      <code className="subline">{p.id}</code>
                    </div>
                    <Badge value="UNVERIFIED" />
                    <ChevronRight className="disclosure-chevron" size={18} />
                  </summary>
                  <div className="proposal-body">
                    <dl>
                      <dt>Branch</dt>
                      <dd><code>{p.branch}</code></dd>
                      <dt>Base revision</dt>
                      <dd><code>{p.base ?? 'Unavailable'}</code></dd>
                      <dt>Stored decision</dt>
                      <dd>{d ? <Badge value={d.outcome} /> : 'Unavailable'}</dd>
                      <dt>Decision identity</dt>
                      <dd><code>{p.decision_id}</code></dd>
                      <dt>Diff / changed files</dt>
                      <dd>Unavailable through the current read-only API.</dd>
                      <dt>Review status</dt>
                      <dd>Proposal inspection mode. Automatic merging is forbidden by policy.</dd>
                    </dl>
                    <pre>{p.body || 'Proposal body unavailable.'}</pre>
                    {d && <p style={{ marginTop: '12px' }}><strong>Policy Rationale:</strong> {d.rationale}</p>}
                    {d?.hypothesis_id && data.investigations.some(h => h.id === d.hypothesis_id) && (
                      <Link className="text-link" to={`/proof/${encodeURIComponent(d.hypothesis_id)}`}>
                        Inspect linked proof <ArrowUpRight size={16} />
                      </Link>
                    )}
                  </div>
                </details>
              )
            })}
          </div>
        ) : (
          <Empty title="No proposal artifacts recorded" icon={GitBranch}>
            A removal decision alone is not a proposal. Only stored PR artifacts appear here; the browser cannot create one.
          </Empty>
        )}
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Recorded policy decisions</h2>
        </div>
        <DecisionList data={data.decisions} />
      </section>
    </>
  )
}

function Integrations({ data }: { data: Snapshot }) {
  return (
    <>
      <PageTitle
        eyebrow="Workspace / System"
        title="Integrations & system health"
        description="Configuration observations are separate from verified operation. Fail-closed on missing credentials."
      />
      <div className="runtime-grid">
        <div className="panel runtime">
          <small>Actual Store</small>
          <h2>{data.health.store}</h2>
          <p>{data.health.store === 'MemoryStore' ? 'Volatile process memory. Records do not survive restart.' : 'Configured application instance; restart durability not tested here.'}</p>
        </div>
        <div className="panel runtime">
          <small>Actual Cache</small>
          <h2>{data.health.cache}</h2>
          <p>Shared with this backend instance. URL presence alone is not connectivity proof.</p>
        </div>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Integration inventory</h2>
          <span className="quiet-label">No paid inference or mutating checks on render</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Integration</th>
                <th>Configuration</th>
                <th>Authentication</th>
                <th>Operation</th>
              </tr>
            </thead>
            <tbody>
              {data.health.integrations.map(i => (
                <tr key={i.name}>
                  <td>
                    <strong>{i.name}</strong>
                    <p className="integration-note">{i.note}</p>
                  </td>
                  <td><Badge value={i.configuration} /></td>
                  <td><Badge value={i.authentication} /></td>
                  <td><Badge value={i.operation} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <div className="notice">
        <LockKeyhole size={17} />
        <span>Credentials are never returned by this inventory. Refresh reads metadata only; it does not authenticate providers or start Docker.</span>
      </div>
    </>
  )
}

function SecurityAudit() {
  return (
    <>
      <PageTitle
        eyebrow="Workspace / Security"
        title="Security & Trust Boundaries"
        description="Technical audit of UNBODGE invariant enforcement and zero self-authorization architecture."
      />
      <IntegrityNote />
      <div className="two-column">
        <section className="panel">
          <div className="panel-heading">
            <h2>Deterministic Policy Gate</h2>
            <ShieldCheck size={18} />
          </div>
          <div className="record">
            <strong>The AI Never Authorizes Its Own Conclusions</strong>
            <p>
              NVIDIA Nemotron operates strictly in an advisory role. It generates causal hypotheses and uncertainties.
              The decision to propose removal or abstain is made by a deterministic policy engine that checks:
            </p>
            <ul style={{ paddingLeft: '20px', color: '#9199a9', fontSize: '11px', lineHeight: '1.8', marginTop: '10px' }}>
              <li>Exact 4-cell counterfactual execution results (A=PASS, B=FAIL, C=PASS, D=PASS).</li>
              <li>Cryptographic SHA-256 evidence item hash integrity.</li>
              <li>Regression test suite execution on the exact workaround-removed tree.</li>
              <li>Git provenance binding to upstream fixing commit and release ancestry.</li>
            </ul>
          </div>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>Process-Local Execution Receipts</h2>
            <LockKeyhole size={18} />
          </div>
          <div className="record">
            <strong>Anti-Replay & Proof Tamper Prevention</strong>
            <p>
              Execution receipts are bound to process memory and cannot be forged, replayed across restarts, or synthesized.
              If an attacker tampers with evidence hashes or falsifies an execution outcome, the proof validator fails closed.
            </p>
            <p style={{ marginTop: '10px' }}>
              <code>PROPOSE_ONLY</code> Invariant: UNBODGE creates proposed branches and PR bodies for human review.
              It possesses zero automatic merge capabilities.
            </p>
          </div>
        </section>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <h2>Provenance Boundary & Live Limitations</h2>
          <ShieldAlert size={18} />
        </div>
        <div className="record">
          <strong>Truthful Capability Boundary</strong>
          <p>
            UNBODGE strictly differentiates between:
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '14px', marginTop: '12px' }}>
            <div style={{ padding: '12px', border: '1px solid var(--line)', borderRadius: '6px', background: '#0e1015' }}>
              <Badge value="PASS" />
              <p style={{ marginTop: '8px', fontSize: '11px' }}><strong>Controlled Fixtures:</strong> Offline, byte-exact reproducible Git mirrors with verified packaging and pip fixtures.</p>
            </div>
            <div style={{ padding: '12px', border: '1px solid var(--line)', borderRadius: '6px', background: '#0e1015' }}>
              <Badge value="PASS" />
              <p style={{ marginTop: '8px', fontSize: '11px' }}><strong>Docker Sandbox:</strong> Real container execution with dropped capabilities (<code>--cap-drop ALL</code>, <code>--network none</code>).</p>
            </div>
            <div style={{ padding: '12px', border: '1px solid var(--line)', borderRadius: '6px', background: '#0e1015' }}>
              <Badge value="UNVERIFIED" />
              <p style={{ marginTop: '8px', fontSize: '11px' }}><strong>Live GitHub Provenance:</strong> Unverified by default without explicit authenticated repository mirrors and upstream signing keys.</p>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}

function Connection({ onConnect }: { onConnect: (token: string) => void }) {
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  function submit(event: FormEvent) {
    event.preventDefault()
    onConnect(value.trim())
    setValue('')
    setOpen(false)
  }
  return (
    <Dialog.Root open={open} onOpenChange={next => { setOpen(next); if (!next) setValue('') }}>
      <Dialog.Trigger asChild>
        <button className="icon-button" aria-label="Connection settings">
          <Settings2 size={18} />
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content">
          <Dialog.Title>Connect to UNBODGE</Dialog.Title>
          <Dialog.Description>
            Use the existing operator API token if this backend requires one. It stays in memory until reload. Never enter GitHub or model-provider credentials.
          </Dialog.Description>
          <form onSubmit={submit}>
            <label className="field-label" htmlFor="operator-token">Operator API token</label>
            <input
              id="operator-token"
              type="password"
              autoComplete="off"
              value={value}
              onChange={e => setValue(e.target.value)}
              maxLength={512}
            />
            <p className="muted text-sm">Leave empty for the backend’s local development mode.</p>
            <button className="button primary" type="submit">Connect</button>
          </form>
          <Dialog.Close className="dialog-close icon-button" aria-label="Close connection settings">
            <X size={18} />
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function App() {
  const [token, setToken] = useState('')
  const [revision, setRevision] = useState(0)
  const [data, setData] = useState<Snapshot | null>(null)
  const [error, setError] = useState('')
  const location = useLocation()
  const main = useRef<HTMLElement>(null)

  useEffect(() => { main.current?.focus({ preventScroll: true }) }, [location.pathname])

  useEffect(() => {
    const controller = new AbortController()
    setData(null)
    setError('')
    request('/snapshot', snapshotSchema, token, controller.signal)
      .then(result => { if (!controller.signal.aborted) setData(result) })
      .catch(e => { if (!controller.signal.aborted) setError(e instanceof ApiError ? e.message : 'Backend unavailable.') })
    return () => controller.abort()
  }, [token, revision])

  const refresh = () => setRevision(n => n + 1)

  return (
    <ConnectionContext.Provider value={{ token, revision }}>
      <a className="skip-link" href="#main">Skip to content</a>
      <div className="app-shell">
        <aside className="sidebar">
          <Link to="/" className="brand">
            <span className="brand-mark"><Braces size={24} strokeWidth={2.3} /></span>
            UNBODGE
            <span className="brand-beta">BETA</span>
          </Link>
          <div className="workspace">
            <div className="workspace-avatar">U</div>
            <div>
              <strong>Evidence operations</strong>
              <small>Local workspace</small>
            </div>
            <ChevronRight size={14} />
          </div>
          <p className="nav-label">WORKSPACE</p>
          <nav aria-label="Main navigation">
            {nav.map(([path, label, Icon]) => (
              <NavLink key={path} to={path} end={path === '/'} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                <Icon size={18} strokeWidth={1.7} />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-footer">
            <div className="safety-label">
              <ShieldCheck size={18} />
              <span>PROPOSE_ONLY</span>
            </div>
            <p>Evidence drives decisions.<br />Merging stays with humans.</p>
            <div className="version-label">
              UNBODGE <span>Read-only console</span>
            </div>
          </div>
        </aside>

        <div className="workspace-main">
          <header className="topbar">
            <div className="breadcrumbs">
              <span>Workspace</span>
              <ChevronRight size={14} />
              <span>{nav.find(([p]) => p === '/' ? location.pathname === '/' : location.pathname.startsWith(p))?.[1] ?? 'Record'}</span>
            </div>
            <div className="topbar-actions">
              <span className="mode-tag"><LockKeyhole size={12} />Read only</span>
              <Connection onConnect={next => { setToken(next); refresh() }} />
              <button className="button compact" onClick={refresh} disabled={!data && !error}>
                <Activity size={14} />Refresh
              </button>
            </div>
          </header>

          <main id="main" ref={main} tabIndex={-1}>
            {error ? (
              <ErrorPanel error={error} retry={refresh} />
            ) : !data ? (
              <div role="status" className="loading">
                <CircleDot size={20} />
                Loading backend observations…
              </div>
            ) : (
              <>
                {data.health.authentication === 'LOCAL_DEV_READ_ONLY' && (
                  <div className="dev-label">
                    Local development · dashboard reads only · existing API writes have no operator token configured
                  </div>
                )}
                {(data.truncated || data.invalid_records > 0) && (
                  <div className="notice danger">
                    {data.truncated && 'Snapshot capped at 200 records per collection. '}
                    {data.invalid_records > 0 && `${data.invalid_records} invalid records omitted. `}
                    Counts may be incomplete.
                  </div>
                )}
                <Routes>
                  <Route path="/" element={<Overview data={data} onConnectRepo={refresh} />} />
                  <Route path="/repositories" element={<RepositoriesView data={data} onRefresh={refresh} />} />
                  <Route path="/investigations" element={<Investigations data={data} />} />
                  <Route path="/investigations/:id" element={<InvestigationDetail />} />
                  <Route path="/proof" element={<Investigations data={data} proof />} />
                  <Route path="/proof/:id" element={<InvestigationDetail proofOnly />} />
                  <Route path="/evidence" element={<GlobalEvidenceLedger data={data} />} />
                  <Route path="/proposals" element={<Proposals data={data} />} />
                  <Route path="/integrations" element={<Integrations data={data} />} />
                  <Route path="/security" element={<SecurityAudit />} />
                  <Route path="*" element={
                    <>
                      <PageTitle eyebrow="Workspace" title="Page not found" description="This route does not exist." />
                      <Link className="button" to="/">Return to overview</Link>
                    </>
                  } />
                </Routes>
                <footer className="page-footer">
                  <span>UNBODGE / Evidence before action</span>
                  <span>Observed {new Date(data.observed_at).toLocaleString()}</span>
                </footer>
              </>
            )}
          </main>
        </div>
      </div>
    </ConnectionContext.Provider>
  )
}
