"""
Confluence Documentation Drift Detection

For each Confluence page, checks whether recent code activity (commits, tickets)
references the topics the page covers. When engineers are actively working on a
topic but the corresponding doc hasn't been updated recently, that gap is the
drift signal.

Drift metric: max(last_related_commit_date, last_related_ticket_date) - page_last_modified_date

    gap < 14 days  → low    (doc is keeping up)
    gap 14-30 days → medium (doc is falling behind)
    gap > 30 days  → high   (doc is stale relative to code activity)
    no code activity found  → none (page covers a topic with no recent code refs)

Topic extraction (Option B — LLM, one call per page, result cached in DB):
    The first run calls Groq to extract 3-5 technical topics per page and stores
    them in confluence_topics. Subsequent runs skip the LLM call unless --refresh
    is passed. This means LLM cost is O(pages), not O(pages × runs).

Usage:
    python scripts/check_confluence_drift.py              # compute and save
    python scripts/check_confluence_drift.py --dry-run    # compute, print, don't save
    python scripts/check_confluence_drift.py --report     # print current saved values
    python scripts/check_confluence_drift.py --refresh    # re-extract topics even if cached
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime, timezone
from typing import Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.utils import timezone as django_tz
from knowledge_base.models import ConfluencePage, GitCommit, JiraTicket

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

DRIFT_LOW_DAYS    = 14
DRIFT_MEDIUM_DAYS = 30

STOP_WORDS = {
    'the', 'for', 'and', 'use', 'with', 'from', 'that', 'this',
    'will', 'our', 'all', 'are', 'was', 'has', 'been', 'into',
    'how', 'what', 'when', 'where', 'why', 'who', 'page', 'section',
    'guide', 'overview', 'introduction', 'summary', 'document',
}


def _as_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _title_keywords(title: str) -> List[str]:
    words = re.sub(r'[^a-z0-9\s]', ' ', title.lower()).split()
    return [w for w in words if len(w) > 3 and w not in STOP_WORDS]


def extract_topics_with_llm(page: ConfluencePage) -> List[str]:
    """Call Groq once to extract 3-5 technical topics from page title + content snippet."""
    try:
        from openai import OpenAI
        groq_key = os.getenv('GROQ_API_KEY')
        if not groq_key:
            return _title_keywords(page.title)

        client = OpenAI(
            api_key=groq_key,
            base_url='https://api.groq.com/openai/v1',
        )

        content_snippet = page.content[:800] if page.content else ''
        prompt = (
            f"Page title: {page.title}\n\n"
            f"Content (first 800 chars):\n{content_snippet}\n\n"
            "List 3-5 specific technical topics this documentation page covers. "
            "Focus on technology names, tools, processes, or concepts that engineers "
            "would mention in commit messages or tickets. "
            "Return ONLY a JSON array of short strings, e.g.: "
            '[\"react\", \"component library\", \"frontend routing\"]'
        )

        response = client.chat.completions.create(
            model='llama-3.1-8b-instant',
            messages=[
                {
                    "role": "system",
                    "content": "You extract technical topics from documentation. Return only valid JSON arrays."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=150,
        )
        raw = response.choices[0].message.content.strip()

        # Parse JSON array from response
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            topics = json.loads(match.group())
            if isinstance(topics, list):
                return [str(t).lower().strip() for t in topics if t]

    except Exception as e:
        print(f"    [LLM] topic extraction failed for '{page.title}': {e}")

    # Fallback: title keywords
    return _title_keywords(page.title)


def get_topics(page: ConfluencePage, refresh: bool = False) -> List[str]:
    """Return cached topics or extract via LLM if not yet computed."""
    if page.confluence_topics and not refresh:
        return page.confluence_topics

    print(f"    [LLM] extracting topics for: {page.title[:60]}")
    topics = extract_topics_with_llm(page)
    return topics


def find_last_code_activity(topics: List[str]) -> Optional[datetime]:
    """Return the most recent commit or ticket date that references any topic."""
    if not topics:
        return None

    latest: Optional[datetime] = None

    for term in topics:
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


def compute_drift_risk(
    page_updated: Optional[datetime],
    last_activity: Optional[datetime],
) -> str:
    """
    Drift = how far code activity has moved ahead of the documentation.

    If there's no code activity for this page's topics, we can't call it
    stale — the topics might just be stable. Return 'none'.
    """
    if last_activity is None:
        return 'none'

    if page_updated is None:
        # Activity exists but we don't know when the doc was last updated → assume stale
        return 'high'

    gap_days = (_as_aware(last_activity) - _as_aware(page_updated)).days

    if gap_days < DRIFT_LOW_DAYS:
        return 'low'
    if gap_days < DRIFT_MEDIUM_DAYS:
        return 'medium'
    return 'high'


RISK_LABEL = {
    'low':    'LOW   ',
    'medium': 'MEDIUM',
    'high':   'HIGH  ',
    'none':   'NONE  ',
    'unknown': 'UNKNWN',
}


def _print_row(risk: str, title: str, doc_date: str, activity_date: str, gap_str: str):
    label = RISK_LABEL.get(risk, risk.upper().ljust(6))
    print(f"  [{label}]  {title:<48}  doc: {doc_date}  activity: {activity_date}{gap_str}")


def run(dry_run: bool = False, report_only: bool = False, refresh_topics: bool = False):
    pages = ConfluencePage.objects.all().order_by('title')
    total = pages.count()

    if total == 0:
        print("No Confluence pages found.")
        return

    print(f"\n{'='*80}")
    if report_only:
        print(f"CONFLUENCE DRIFT REPORT  (current saved values, {total} pages)")
    elif dry_run:
        print(f"CONFLUENCE DRIFT CHECK   (dry run — no writes, {total} pages)")
    else:
        print(f"CONFLUENCE DRIFT CHECK   (computing and saving, {total} pages)")
    print(f"{'='*80}\n")

    counts = {'low': 0, 'medium': 0, 'high': 0, 'none': 0}

    for page in pages:
        if report_only:
            risk = page.drift_risk or 'unknown'
            doc_date = (
                page.page_updated_date.strftime('%Y-%m-%d')
                if page.page_updated_date else 'unknown'
            )
            activity_date = (
                page.last_activity_date.strftime('%Y-%m-%d')
                if page.last_activity_date else 'none'
            )
            gap_str = ''
            if page.last_activity_date and page.page_updated_date:
                gap = (_as_aware(page.last_activity_date) - _as_aware(page.page_updated_date)).days
                gap_str = f'  (gap: {gap}d)'
            topics_str = ', '.join(page.confluence_topics or [])
            _print_row(risk, page.title[:48], doc_date, activity_date, gap_str)
            if topics_str:
                print(f"           topics: {topics_str}")
            counts[risk] = counts.get(risk, 0) + 1
            continue

        # Compute
        topics = get_topics(page, refresh=refresh_topics)
        last_activity = find_last_code_activity(topics)
        risk = compute_drift_risk(page.page_updated_date, last_activity)
        counts[risk] = counts.get(risk, 0) + 1

        doc_date = (
            page.page_updated_date.strftime('%Y-%m-%d')
            if page.page_updated_date else 'unknown'
        )
        activity_date = last_activity.strftime('%Y-%m-%d') if last_activity else 'none'
        gap_str = ''
        if last_activity and page.page_updated_date:
            gap = (_as_aware(last_activity) - _as_aware(page.page_updated_date)).days
            gap_str = f'  (gap: {gap}d)'

        topics_str = ', '.join(topics)
        _print_row(risk, page.title[:48], doc_date, activity_date, gap_str)
        print(f"           topics: {topics_str}")

        if not dry_run:
            page.confluence_topics = topics
            page.last_activity_date = last_activity
            page.drift_risk = risk
            page.save(update_fields=['confluence_topics', 'last_activity_date', 'drift_risk'])

    print(f"\n{'─'*80}")
    print(f"  Low risk    : {counts.get('low', 0)}  (doc updated within {DRIFT_LOW_DAYS}d of latest code activity)")
    print(f"  Medium risk : {counts.get('medium', 0)}  (gap {DRIFT_LOW_DAYS}–{DRIFT_MEDIUM_DAYS} days)")
    print(f"  High risk   : {counts.get('high', 0)}  (gap > {DRIFT_MEDIUM_DAYS} days — doc is stale)")
    print(f"  No activity : {counts.get('none', 0)}  (no commits/tickets reference these topics)")

    if dry_run:
        print(f"\n  [DRY RUN] No changes written.")
    elif not report_only:
        print(f"\n  Saved drift status for {total} confluence pages.")
        print(f"  Query high-risk pages:")
        print(f"    ConfluencePage.objects.filter(drift_risk='high')")


def main():
    parser = argparse.ArgumentParser(description='Compute Confluence documentation drift risk')
    parser.add_argument('--dry-run', action='store_true',
                        help='Compute and print results without saving')
    parser.add_argument('--report', action='store_true',
                        help='Print current saved drift_risk values without recomputing')
    parser.add_argument('--refresh', action='store_true',
                        help='Re-extract LLM topics even if already cached in DB')
    args = parser.parse_args()
    run(dry_run=args.dry_run, report_only=args.report, refresh_topics=args.refresh)


if __name__ == '__main__':
    main()
