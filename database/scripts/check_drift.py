"""
Decision Drift Detection

Scans every active decision and checks whether the technologies or concepts
it references are still appearing in recent commits and Jira tickets.

A decision is "reinforced" when a commit message or ticket summary contains
one of its tags (or a keyword from its title if tags are empty). The most
recent reinforcement date is stored as last_reinforced_at. drift_risk is then
computed from how long ago that was:

    < 30 days  → low
    30-90 days → medium
    > 90 days  → high
    never seen → high

Usage:
    python scripts/check_drift.py              # compute and save
    python scripts/check_drift.py --dry-run    # compute, print, don't save
    python scripts/check_drift.py --report     # print current saved values
"""

import os
import sys
import argparse
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.utils import timezone as django_tz
from knowledge_base.models import Decision, GitCommit, JiraTicket

DRIFT_LOW_DAYS  = 30
DRIFT_HIGH_DAYS = 90

STOP_WORDS = {
    'the', 'for', 'and', 'use', 'with', 'from', 'that', 'this',
    'will', 'our', 'all', 'are', 'was', 'has', 'been', 'into',
}


def _as_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def compute_drift_risk(last_reinforced_at: Optional[datetime]) -> str:
    if last_reinforced_at is None:
        return 'high'
    days_ago = (django_tz.now() - _as_aware(last_reinforced_at)).days
    if days_ago < DRIFT_LOW_DAYS:
        return 'low'
    if days_ago < DRIFT_HIGH_DAYS:
        return 'medium'
    return 'high'


def _search_terms(decision: Decision) -> list:
    """Tags if present, otherwise meaningful words extracted from the title."""
    if decision.tags:
        return [t.lower() for t in decision.tags]
    words = decision.title.lower().split()
    return [w for w in words if len(w) > 3 and w not in STOP_WORDS]


def find_last_reinforcement(decision: Decision) -> Optional[datetime]:
    """Return the most recent date any term appears in commits or tickets."""
    terms = _search_terms(decision)
    if not terms:
        return None

    latest: Optional[datetime] = None

    for term in terms:
        commit = (
            GitCommit.objects
            .filter(message__icontains=term)
            .order_by('-commit_date')
            .first()
        )
        if commit and commit.commit_date:
            dt = _as_aware(commit.commit_date)
            if latest is None or dt > latest:
                latest = dt

        ticket = (
            JiraTicket.objects
            .filter(summary__icontains=term)
            .order_by('-updated_date')
            .first()
        )
        if ticket and ticket.updated_date:
            dt = _as_aware(ticket.updated_date)
            if latest is None or dt > latest:
                latest = dt

    return latest


RISK_LABEL = {'low': 'LOW   ', 'medium': 'MEDIUM', 'high': 'HIGH  '}
RISK_COLOR = {'low': '', 'medium': '', 'high': ''}  # extend with ANSI if needed


def _print_row(risk: str, title: str, date_str: str, days_str: str):
    label = RISK_LABEL.get(risk, risk.upper())
    print(f"  [{label}]  {title:<52}  last seen: {date_str}{days_str}")


def run(dry_run: bool = False, report_only: bool = False):
    decisions = Decision.objects.filter(status='active').order_by('category', 'decision_date')
    total = decisions.count()

    if total == 0:
        print("No active decisions found.")
        return

    print(f"\n{'='*70}")
    if report_only:
        print(f"DRIFT REPORT  (current saved values, {total} active decisions)")
    elif dry_run:
        print(f"DRIFT CHECK   (dry run — no writes, {total} active decisions)")
    else:
        print(f"DRIFT CHECK   (computing and saving, {total} active decisions)")
    print(f"{'='*70}\n")

    counts = {'low': 0, 'medium': 0, 'high': 0}
    current_category = None

    for d in decisions:
        if d.category != current_category:
            current_category = d.category
            print(f"\n  ── {(current_category or 'uncategorized').upper()} ──")

        if report_only:
            risk = d.drift_risk or 'unknown'
            date_str = (
                d.last_reinforced_at.strftime('%Y-%m-%d')
                if d.last_reinforced_at else 'never'
            )
            days_str = ''
            if d.last_reinforced_at:
                days = (django_tz.now() - _as_aware(d.last_reinforced_at)).days
                days_str = f'  ({days}d ago)'
            _print_row(risk, d.title[:52], date_str, days_str)
            counts[risk] = counts.get(risk, 0) + 1
            continue

        last_seen = find_last_reinforcement(d)
        risk = compute_drift_risk(last_seen)
        counts[risk] += 1

        date_str = last_seen.strftime('%Y-%m-%d') if last_seen else 'never'
        days_str = ''
        if last_seen:
            days = (django_tz.now() - last_seen).days
            days_str = f'  ({days}d ago)'

        _print_row(risk, d.title[:52], date_str, days_str)

        if not dry_run:
            d.last_reinforced_at = last_seen
            d.drift_risk = risk
            d.save(update_fields=['last_reinforced_at', 'drift_risk'])

    print(f"\n{'─'*70}")
    print(f"  Low risk    : {counts.get('low', 0)}")
    print(f"  Medium risk : {counts.get('medium', 0)}")
    print(f"  High risk   : {counts.get('high', 0)}")

    if dry_run:
        print(f"\n  [DRY RUN] No changes written.")
    elif not report_only:
        print(f"\n  Saved drift status for {total} decisions.")
        print(f"  Query high-risk decisions:")
        print(f"    Decision.objects.filter(status='active', drift_risk='high')")


def main():
    parser = argparse.ArgumentParser(description='Compute decision drift risk')
    parser.add_argument('--dry-run', action='store_true',
                        help='Compute and print results without saving')
    parser.add_argument('--report', action='store_true',
                        help='Print current saved drift_risk values without recomputing')
    args = parser.parse_args()
    run(dry_run=args.dry_run, report_only=args.report)


if __name__ == '__main__':
    main()
