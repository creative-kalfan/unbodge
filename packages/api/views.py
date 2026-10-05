"""Judge-facing views (Phase 4). Server-rendered HTML over stored state.

Four views only: dashboard, investigation/causal graph, proof view,
evidence ledger + PR view. No chatbot, no business logic, no JS
frameworks: everything renders from structured records with stdlib
escaping. Evidence is always the scrubbed public representation.
"""

from __future__ import annotations

import html

from fastapi.responses import HTMLResponse

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:sans-serif;max-width:960px;margin:2em auto;padding:0 1em}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.4em;text-align:left}}
.pass{{color:green;font-weight:bold}}.fail{{color:red;font-weight:bold}}
nav a{{margin-right:1em}}</style></head>
<body><nav><a href="/ui/">Dashboard</a><a href="/ui/graph">Causal graph</a>
<a href="/ui/evidence">Evidence ledger</a><a href="/ui/prs">PRs</a></nav>
<h1>{title}</h1>{body}</body></html>"""


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(PAGE.format(title=html.escape(title), body=body))


def _text(value: object) -> str:
    """Escape untrusted record values; non-scalars render empty."""
    if isinstance(value, bool):
        return html.escape(str(value))
    if isinstance(value, (str, int, float)):
        return html.escape(str(value))
    return ""


def _row(record: object) -> dict:
    """Coerce a stored row to a dict (poisoned rows render empty)."""
    return record if isinstance(record, dict) else {}


def _cell(value: object) -> str:
    text = html.escape("" if value is None else str(value))
    if text in ("PASS", "PROPOSE_REMOVAL"):
        return f'<td class="pass">{text}</td>'
    if text in ("FAIL", "ABSTAIN"):
        return f'<td class="fail">{text}</td>'
    return f"<td>{text}</td>"


def dashboard(store) -> HTMLResponse:
    repos = store.list("repositories")
    events = store.list("upstream_events")
    candidates = store.list("workaround_candidates")
    decisions = store.list("decisions")
    prs = store.list("pr_results")
    removals = [d for d in decisions if d.get("outcome") == "PROPOSE_REMOVAL"]
    abstentions = [d for d in decisions if d.get("outcome") == "ABSTAIN"]
    rows = "".join(
        f"<tr><td>{_text(_row(d).get('id'))}</td>"
        f"{_cell(_row(d).get('outcome'))}"
        f"<td>{_text(str(_row(d).get('rationale', ''))[:160])}</td></tr>"
        for d in decisions
    )
    body = (
        f"<p>Watched repositories: <b>{len(repos)}</b> | upstream events: "
        f"<b>{len(events)}</b> | candidates: <b>{len(candidates)}</b> | "
        f"proposed removals: <b>{len(removals)}</b> | PRs: <b>{len(prs)}</b> | "
        f"abstentions: <b>{len(abstentions)}</b></p>"
        "<h2>Decisions</h2><table><tr><th>id</th><th>outcome</th><th>rationale</th></tr>"
        f"{rows}</table>"
    )
    return _page("UNBODGE dashboard", body)


def causal_graph(store) -> HTMLResponse:
    from evidence.scrub import scrub_item
    from domain.models import EvidenceItem

    items = []
    for record in store.list("evidence"):
        try:
            items.append(scrub_item(EvidenceItem(**record)))
        except Exception:
            continue
    links = store.list("evidence_links")
    if not items:
        return _page("Causal graph", "<p>No evidence recorded yet.</p>")
    width = max(640, 180 * len(items))
    nodes = []
    for index, item in enumerate(items):
        x = 20 + index * 170
        label = html.escape(f"{item.evidence_type.value}: {item.claim[:42]}")
        nodes.append(
            f'<g><rect x="{x}" y="60" width="150" height="64" fill="#eef" stroke="#333"/>'
            f'<text x="{x + 6}" y="84" font-size="10">{label}</text>'
            f'<text x="{x + 6}" y="102" font-size="9">{html.escape(item.evidence_id[:24])}</text></g>'
        )
        if index:
            prev = 20 + (index - 1) * 170 + 150
            nodes.append(
                f'<line x1="{prev}" y1="92" x2="{x}" y2="92" stroke="#333" '
                f'marker-end="url(#a)"/>'
            )
    known = {item.evidence_id for item in items}
    dangling = [l for l in links if l.get("from_id") not in known or l.get("to_id") not in known]
    svg = (
        f'<svg width="{width}" height="180" xmlns="http://www.w3.org/2000/svg">'
        '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" '
        'orient="auto"><path d="M0,0 L8,4 L0,8" fill="#333"/></marker></defs>'
        + "".join(nodes) + "</svg>"
    )
    chain = "issue &rarr; fix &rarr; release &rarr; behavior &rarr; workaround &rarr; experiment &rarr; evidence"
    warn = f"<p>Dangling links ignored: {len(dangling)}</p>" if dangling else ""
    return _page("Investigation / causal graph", f"<p>{chain}</p>{svg}{warn}")


def proof_view(store, result_id: str) -> HTMLResponse:
    record = store.get("experiments", result_id)
    if not isinstance(record, dict):
        return HTMLResponse("proof not found", status_code=404)
    matrix = record.get("matrix", {})
    if not isinstance(matrix, dict):
        matrix = {}
    runs = [r for r in store.list("experiment_runs") if isinstance(r, dict)]
    rows = ""
    for cell in ("A", "B", "C", "D"):
        run = None
        for candidate in runs:
            if str(candidate.get("spec_id", "")).endswith(f":cell:{cell}"):
                run = candidate
                break
        run = run or {}
        env = run.get("environment", {})
        if not isinstance(env, dict):
            env = {}
        rows += (
            f"<tr><td>{cell}</td>"
            f"<td>{html.escape(str(run.get('dependency_state', {})))}</td>"
            f"<td>{html.escape(str(env.get('WORKAROUND', '?')))}</td>"
            f"{_cell(matrix.get(cell, '?'))}"
            f"<td>{html.escape(str(run.get('exit_code', '?')))}</td>"
            f"<td>{html.escape(str(run.get('duration_s', '?')))}</td>"
            f"<td>{html.escape(str(run.get('artifact_hashes', {}))[:120])}</td></tr>"
        )
    body = (
        "<table><tr><th>cell</th><th>dependency</th><th>workaround</th>"
        "<th>result</th><th>exit</th><th>duration_s</th><th>artifacts</th></tr>"
        f"{rows}</table>"
    )
    return _page(f"Proof {result_id}", body)


def evidence_ledger(store) -> HTMLResponse:
    from evidence.scrub import scrub_item
    from domain.models import EvidenceItem

    rows = ""
    for record in store.list("evidence"):
        try:
            item = scrub_item(EvidenceItem(**record))
        except Exception:
            continue
        rows += (
            f"<tr><td>{html.escape(item.evidence_id)}</td>"
            f"<td>{html.escape(item.evidence_type.value)}</td>"
            f"<td>{html.escape(item.source)}</td>"
            f"<td>{html.escape(item.claim[:120])}</td>"
            f"<td><code>{html.escape(item.hash[:16])}…</code></td>"
            f"<td>{html.escape(str(item.timestamp))}</td>"
            f"<td>{html.escape(item.experiment_id or '')}</td></tr>"
        )
    body = (
        "<table><tr><th>id</th><th>type</th><th>source</th><th>claim</th>"
        "<th>hash</th><th>timestamp</th><th>experiment</th></tr>" + rows + "</table>"
    )
    return _page("Evidence ledger", body)


def pr_list(store) -> HTMLResponse:
    import urllib.parse

    def _link(row: object) -> str:
        record = _row(row)
        raw_id = record.get("id")
        raw_id = raw_id if isinstance(raw_id, str) else ""
        target = urllib.parse.quote(raw_id, safe="")
        return (
            f"<tr><td><a href=\"/ui/prs/{target}\">{_text(raw_id)}</a></td>"
            f"<td>{_text(str(record.get('title', ''))[:100])}</td>"
            f"<td>{_text(record.get('branch'))}</td></tr>"
        )

    rows = "".join(_link(p) for p in store.list("pr_results"))
    return _page(
        "PRs",
        "<table><tr><th>id</th><th>title</th><th>branch</th></tr>" + rows + "</table>",
    )


def pr_detail(store, pr_id: str) -> HTMLResponse:
    record = store.get("pr_results", pr_id)
    if not isinstance(record, dict):
        return HTMLResponse("PR not found", status_code=404)
    decision_key = record.get("decision_id", "")
    decision = store.get("decisions", decision_key) if isinstance(decision_key, str) else None
    decision = decision or {}
    abstention = ""
    if decision.get("outcome") == "ABSTAIN":
        abstention = f"<p>Abstention reason: {_text(decision.get('rationale'))}</p>"
    body = (
        f"<h2>{_text(record.get('title'))}</h2>"
        f"<p>Branch <code>{_text(record.get('branch'))}</code> &larr; "
        f"<code>{_text(record.get('base'))}</code></p>"
        f"<pre>{_text(record.get('body'))}</pre>"
        f"<p>Policy decision: <b>{_text(decision.get('outcome', '?'))}</b></p>"
        f"<p>{_text(decision.get('rationale'))}</p>{abstention}"
    )
    return _page(f"PR {pr_id}", body)


__all__ = ["causal_graph", "dashboard", "evidence_ledger", "pr_detail", "pr_list", "proof_view"]
