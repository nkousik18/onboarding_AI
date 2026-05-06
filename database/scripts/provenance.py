"""
Decision Provenance Chain

For any decision, traces the full chain of evidence across all data sources:

    Meeting / Confluence / Jira
        └── Decision made
            ├── Jira tickets linked to the source
            │   └── Git commits that reference those tickets
            ├── Commits after the decision date that mention decision tags
            ├── Active conflicts (from check_conflicts.py)
            └── Supersession chain (if decision was overridden)

This answers questions like:
    "Where did the decision to use ECS Fargate come from?"
    "What code was written as a result of the Tailwind CSS switch?"
    "Show me the full history behind the SQLAlchemy decision."

Usage:
    python scripts/provenance.py --decision "Use SQLAlchemy"
    python scripts/provenance.py --id <uuid>
    python scripts/provenance.py --all          # print summary for every decision
    python scripts/provenance.py --json         # output raw JSON
"""

import os
import sys
import json
import argparse
import uuid as uuid_lib
from datetime import date, datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from knowledge_base.models import (
    Decision, DecisionConflict,
    Meeting, ConfluencePage, JiraTicket,
    GitCommit, EntityReference,
)


# ── Core traversal ─────────────────────────────────────────────────────────

def _safe_date(val) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val.strftime('%Y-%m-%d')
    return str(val)[:10]


def _find_tickets_for_source(source_type: str, source_id) -> list[str]:
    """Ticket keys linked to a source via EntityReference."""
    refs = EntityReference.objects.filter(
        source_type=source_type,
        source_id=source_id,
        reference_type='jira_ticket',
    )
    keys = [r.reference_id for r in refs if r.reference_id and not r.reference_id[:4].isdigit()]
    return list(set(keys))


def _commits_for_tickets(ticket_keys: list[str]) -> list[dict]:
    """Commits that reference any of the given ticket keys."""
    commits = {}
    for key in ticket_keys:
        # Via EntityReference (commit -> jira_ticket)
        for ref in EntityReference.objects.filter(
            source_type='commit',
            reference_type='jira_ticket',
            reference_id=key,
        ):
            gc = GitCommit.objects.filter(id=ref.source_id).first()
            if gc and str(gc.id) not in commits:
                commits[str(gc.id)] = {
                    'sha':    gc.sha[:8] if gc.sha else str(gc.id)[:8],
                    'message': gc.message.split('\n')[0][:100],
                    'author':  gc.author_name,
                    'date':    _safe_date(gc.commit_date),
                    'via_ticket': key,
                }
        # Via GitCommit.related_tickets array
        for gc in GitCommit.objects.filter(related_tickets__contains=[key]):
            if str(gc.id) not in commits:
                commits[str(gc.id)] = {
                    'sha':     gc.sha[:8] if gc.sha else str(gc.id)[:8],
                    'message': gc.message.split('\n')[0][:100],
                    'author':  gc.author_name,
                    'date':    _safe_date(gc.commit_date),
                    'via_ticket': key,
                }
    return sorted(commits.values(), key=lambda c: c['date'] or '')


def _commits_for_tags(tags: list[str], after_date: Optional[date]) -> list[dict]:
    """Commits after the decision date that mention any of the decision's tags."""
    if not tags:
        return []
    seen = set()
    results = []
    for tag in tags:
        qs = GitCommit.objects.filter(message__icontains=tag)
        if after_date:
            qs = qs.filter(commit_date__date__gte=after_date)
        for gc in qs.order_by('commit_date')[:10]:
            if str(gc.id) not in seen:
                seen.add(str(gc.id))
                results.append({
                    'sha':     gc.sha[:8] if gc.sha else str(gc.id)[:8],
                    'message': gc.message.split('\n')[0][:100],
                    'author':  gc.author_name,
                    'date':    _safe_date(gc.commit_date),
                    'via_tag': tag,
                })
    return sorted(results, key=lambda c: c['date'] or '')


def _load_origin(source_type: str, source_id) -> Optional[dict]:
    if source_type == 'meeting':
        m = Meeting.objects.filter(id=source_id).first()
        if not m:
            return None
        parts = []
        if m.participants:
            import re
            parts = list(set(re.findall(r'[A-Z][a-z]+ [A-Z][a-z]+', m.participants)))[:8]
        return {
            'type':         'meeting',
            'title':        m.title,
            'date':         _safe_date(m.meeting_date),
            'participants': parts,
        }
    if source_type == 'confluence':
        cp = ConfluencePage.objects.filter(id=source_id).first()
        if not cp:
            return None
        return {
            'type':   'confluence',
            'title':  cp.title,
            'date':   _safe_date(cp.page_created_date),
            'author': cp.author,
            'labels': cp.labels or [],
        }
    if source_type == 'jira':
        jt = JiraTicket.objects.filter(id=source_id).first()
        if jt:
            return {
                'type':     'jira',
                'title':    jt.summary,
                'key':      jt.issue_key,
                'date':     _safe_date(jt.created_date),
                'assignee': jt.assignee,
            }
    return {'type': source_type, 'title': str(source_id)}


def _load_conflicts(decision: Decision) -> list[dict]:
    conflicts = []
    for c in DecisionConflict.objects.filter(decision_a=decision).select_related('decision_b'):
        conflicts.append({
            'other_title': c.decision_b.title,
            'type':        c.conflict_type,
            'severity':    c.severity,
            'explanation': c.explanation,
        })
    for c in DecisionConflict.objects.filter(decision_b=decision).select_related('decision_a'):
        conflicts.append({
            'other_title': c.decision_a.title,
            'type':        c.conflict_type,
            'severity':    c.severity,
            'explanation': c.explanation,
        })
    return conflicts


def get_provenance_chain(decision: Decision) -> dict:
    """Return the full provenance chain for a decision as a structured dict."""

    # Origin source
    origin = _load_origin(decision.source_type, decision.source_id) if decision.source_id else None

    # Ticket keys: from EntityReference on the source + decision.related_tickets
    ticket_keys = []
    if decision.source_id:
        ticket_keys = _find_tickets_for_source(decision.source_type, decision.source_id)
    if decision.related_tickets:
        ticket_keys = list(set(ticket_keys + decision.related_tickets))

    # Jira ticket details
    tickets = []
    for key in ticket_keys:
        jt = JiraTicket.objects.filter(issue_key=key).first()
        if jt:
            tickets.append({
                'key':      jt.issue_key,
                'summary':  jt.summary,
                'status':   jt.status,
                'assignee': jt.assignee,
                'date':     _safe_date(jt.created_date),
            })
        else:
            tickets.append({'key': key, 'summary': None, 'status': None, 'assignee': None, 'date': None})

    # Commits: via ticket refs + tag keyword scan after decision date
    commits_via_tickets = _commits_for_tickets(ticket_keys)
    commits_via_tags    = _commits_for_tags(decision.tags or [], decision.decision_date)

    # Merge, deduplicate by sha, prefer ticket-linked entries
    seen_sha = {c['sha'] for c in commits_via_tickets}
    for c in commits_via_tags:
        if c['sha'] not in seen_sha:
            seen_sha.add(c['sha'])
            commits_via_tickets.append(c)
    all_commits = sorted(commits_via_tickets, key=lambda c: c['date'] or '')

    # Conflicts
    conflicts = _load_conflicts(decision)

    # Supersession
    superseded_by = None
    if decision.superseded_by:
        sup = decision.superseded_by
        superseded_by = {
            'id':    str(sup.id),
            'title': sup.title,
            'date':  _safe_date(sup.decision_date),
        }

    return {
        'decision': {
            'id':          str(decision.id),
            'title':       decision.title,
            'date':        _safe_date(decision.decision_date),
            'status':      decision.status,
            'category':    decision.category,
            'rationale':   decision.rationale,
            'tags':        decision.tags or [],
            'decided_by':  decision.decided_by or [],
            'confidence':  decision.confidence_score,
            'drift_risk':  decision.drift_risk,
        },
        'origin':       origin,
        'tickets':      tickets,
        'commits':      all_commits,
        'conflicts':    conflicts,
        'superseded_by': superseded_by,
    }


# ── CLI display ────────────────────────────────────────────────────────────

SEV = {'high': '!!', 'medium': '~ ', 'low': '  '}

def _print_chain(chain: dict):
    d   = chain['decision']
    org = chain['origin']

    print()
    print('═' * 64)
    status_tag = f"[{d['status'].upper()}]" if d['status'] != 'active' else ''
    print(f"  {d['title']} {status_tag}")
    print(f"  {d['date']}  ·  {d['category'] or 'uncategorised'}  ·  confidence: {d['confidence'] or '?'}")
    if d['tags']:
        print(f"  tags: {', '.join(d['tags'])}")
    if d['drift_risk']:
        print(f"  drift: {d['drift_risk']}")
    print('═' * 64)

    # Rationale
    if d['rationale']:
        print(f"\n  WHY\n  {d['rationale'][:200]}")

    # Origin
    print(f"\n  ORIGIN  ({org['type'] if org else 'unknown'})")
    if org:
        print(f"  ├─ {org['title']}")
        if org.get('date'):
            print(f"  ├─ date: {org['date']}")
        if org.get('participants'):
            print(f"  ├─ participants: {', '.join(org['participants'])}")
        if org.get('author'):
            print(f"  └─ author: {org['author']}")
        if org.get('labels'):
            print(f"  └─ labels: {', '.join(org['labels'])}")
    else:
        print('  └─ (source not found)')

    # Tickets
    tickets = chain['tickets']
    print(f"\n  TICKETS  ({len(tickets)})")
    if tickets:
        for t in tickets:
            status = f"[{t['status']}]" if t['status'] else ''
            assignee = f"→ {t['assignee']}" if t['assignee'] else ''
            summary = t['summary'][:60] if t['summary'] else '(no summary)'
            print(f"  ├─ {t['key']}  {status}  {summary}  {assignee}")
    else:
        print('  └─ none linked')

    # Commits
    commits = chain['commits']
    print(f"\n  COMMITS  ({len(commits)})")
    if commits:
        for c in commits[:10]:
            via = f"via {c.get('via_ticket') or c.get('via_tag', '?')}"
            print(f"  ├─ [{c['date']}]  {c['sha']}  {c['message'][:65]}")
            print(f"  │   {c['author']}  ·  {via}")
        if len(commits) > 10:
            print(f"  └─ ... {len(commits) - 10} more")
    else:
        print('  └─ none found')

    # Conflicts
    conflicts = chain['conflicts']
    print(f"\n  CONFLICTS  ({len(conflicts)})")
    if conflicts:
        for c in conflicts:
            marker = SEV.get(c['severity'], '  ')
            print(f"  [{marker}] {c['severity'].upper()}  ↔  {c['other_title'][:55]}")
            print(f"        type: {c['type']}")
            if c['explanation']:
                print(f"        {c['explanation'][:120]}")
    else:
        print('  └─ none detected')

    # Superseded
    if chain['superseded_by']:
        sup = chain['superseded_by']
        print(f"\n  SUPERSEDED BY")
        print(f"  └─ [{sup['date']}]  {sup['title']}")

    print()


def _find_decision(query: str) -> Optional[Decision]:
    """Find by UUID or partial title match."""
    try:
        uid = uuid_lib.UUID(query)
        return Decision.objects.filter(id=uid).first()
    except ValueError:
        pass
    # Case-insensitive partial title match
    results = Decision.objects.filter(title__icontains=query)
    if results.count() == 1:
        return results.first()
    if results.count() > 1:
        print(f"  Multiple decisions match '{query}':")
        for r in results[:6]:
            print(f"    [{r.id}]  {r.title}")
        print("  Use --id to specify.")
        return None
    return None


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Trace provenance chain for a decision')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--decision', type=str,   help='Partial title to look up')
    group.add_argument('--id',       type=str,   help='Decision UUID')
    group.add_argument('--all',      action='store_true', help='Print summary for all decisions')
    parser.add_argument('--json',    action='store_true', help='Output raw JSON')
    args = parser.parse_args()

    if args.all:
        decisions = Decision.objects.all().order_by('decision_date')
        print(f'Provenance chains for {decisions.count()} decisions\n')
        for d in decisions:
            chain = get_provenance_chain(d)
            if args.json:
                print(json.dumps(chain, indent=2, default=str))
            else:
                _print_chain(chain)
        return

    query = args.id or args.decision
    if not query:
        parser.print_help()
        return

    decision = _find_decision(query)
    if not decision:
        print(f"No decision found for: '{query}'")
        return

    chain = get_provenance_chain(decision)

    if args.json:
        print(json.dumps(chain, indent=2, default=str))
    else:
        _print_chain(chain)


if __name__ == '__main__':
    main()
