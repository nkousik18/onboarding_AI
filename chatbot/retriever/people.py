"""
PeopleRegistry — DB-backed person lookup and evidence-based topic attribution.

Replaces every hardcoded name/role dict in the chatbot.
Loaded once at startup from the Employee table; refreshable at runtime.

Key capabilities:
  find_employees(text)       — fuzzy match against name, role, department
  normalize_name(text)       — partial name → canonical full name
  get_all_names()            — for building classifier patterns
  get_topic_contributors(topic) — who worked on X, ranked by evidence count
  get_person_work(name)      — all commits, tickets, decisions for a person
"""

import sys
import os
import re
from collections import Counter
from typing import Optional

RETRIEVER_DIR = os.path.dirname(os.path.abspath(__file__))
CHATBOT_DIR   = os.path.dirname(RETRIEVER_DIR)
if CHATBOT_DIR not in sys.path:
    sys.path.insert(0, CHATBOT_DIR)

from django_setup import get_models
from django.db.models import Q

_models = get_models()
Employee    = _models['Employee']
GitCommit   = _models['GitCommit']
JiraTicket  = _models['JiraTicket']
Decision    = _models['Decision']


class PeopleRegistry:
    """
    Single source of truth for person data in the chatbot.
    All name lookups and role mappings derive from the Employee table
    and actual work data — nothing is hardcoded.
    """

    def __init__(self):
        self._employees: list[dict] = []    # [{name, role, dept, github, first, last}, ...]
        self._name_index: dict = {}          # lowercase variant → canonical full name
        self.load()

    # ── Loading ────────────────────────────────────────────────────────────

    def load(self):
        """Load/refresh from DB. Safe to call at any time."""
        self._employees = []
        self._name_index = {}

        for emp in Employee.objects.filter(is_active=True).order_by('name'):
            parts = emp.name.split()
            first = parts[0] if parts else emp.name
            last  = parts[-1] if len(parts) > 1 else ''

            record = {
                'name':       emp.name,
                'first':      first,
                'last':       last,
                'role':       emp.role or '',
                'department': emp.department or '',
                'github':     emp.github_username or '',
            }
            self._employees.append(record)

            # Build lookup variants: full name, first name, last name, github handle
            for variant in [emp.name, first, last, emp.github_username or '']:
                key = variant.strip().lower()
                if key:
                    self._name_index[key] = emp.name

    # ── Name resolution ────────────────────────────────────────────────────

    def normalize_name(self, text: str) -> Optional[str]:
        """'marcus' or 'Marcus' or 'marcust' → 'Marcus Thompson'."""
        if not text:
            return None
        return self._name_index.get(text.strip().lower())

    def find_employees(self, text: str) -> list[dict]:
        """
        Return all employees whose name, role, or department match text.
        Used for queries like 'who works on frontend?' or 'who is the tech lead?'
        """
        text_lower = text.lower()
        matches = []
        seen = set()
        for emp in self._employees:
            if emp['name'] in seen:
                continue
            if (text_lower in emp['name'].lower() or
                text_lower in emp['role'].lower() or
                text_lower in emp['department'].lower() or
                text_lower in emp['github'].lower()):
                matches.append(emp)
                seen.add(emp['name'])
        return matches

    def get_all_names(self) -> list[str]:
        """All canonical full names. Used to build classifier patterns."""
        return [emp['name'] for emp in self._employees]

    def get_all_first_names(self) -> list[str]:
        return [emp['first'] for emp in self._employees if emp['first']]

    def name_variants_for_classifier(self) -> list[str]:
        """All name variants in lowercase for keyword detection."""
        return list(self._name_index.keys())

    # ── Evidence-based attribution ─────────────────────────────────────────

    def get_topic_contributors(self, topic: str) -> list[tuple[str, int]]:
        """
        Who worked on a given topic? Ranked by evidence count across
        commits, tickets, and decisions — no hardcoded mapping.

        Returns: [(name, score), ...] sorted descending.
        """
        scores: Counter = Counter()

        # Commits mentioning the topic
        for gc in GitCommit.objects.filter(message__icontains=topic):
            if gc.author_name:
                name = self.normalize_name(gc.author_name.split()[0]) or gc.author_name
                scores[name] += 3  # commits are strongest signal

        # Tickets about the topic
        for jt in JiraTicket.objects.filter(
            Q(summary__icontains=topic) | Q(description__icontains=topic)
        ):
            if jt.assignee:
                name = self.normalize_name(jt.assignee.split()[0]) or jt.assignee
                scores[name] += 2

        # Decisions tagged with or mentioning the topic
        for d in Decision.objects.filter(
            Q(title__icontains=topic) |
            Q(tags__icontains=[topic]) |
            Q(description__icontains=topic)
        ):
            for person in (d.decided_by or []):
                name = self.normalize_name(person.split()[0]) or person
                scores[name] += 1

        return scores.most_common()

    # ── Full work profile for a person ─────────────────────────────────────

    def get_person_work(self, name: str) -> dict:
        """
        Aggregate everything a person has done across all data sources.
        Returns a dict with commits, tickets, decisions.
        """
        # Resolve to canonical name
        canonical = self.normalize_name(name) or name
        first = canonical.split()[0]

        commits = list(
            GitCommit.objects.filter(author_name__icontains=first)
            .order_by('-commit_date')[:10]
        )

        tickets = list(
            JiraTicket.objects.filter(
                Q(assignee__icontains=first) | Q(reporter__icontains=first)
            ).order_by('-updated_date')[:10]
        )

        decisions = list(
            Decision.objects.filter(decided_by__icontains=first)
            .order_by('-decision_date')[:5]
        )

        # Find their role from Employee table
        emp = next((e for e in self._employees
                    if e['name'].lower() == canonical.lower()), None)

        return {
            'name':      canonical,
            'role':      emp['role'] if emp else 'Unknown',
            'commits':   commits,
            'tickets':   tickets,
            'decisions': decisions,
        }

    # ── Role-based lookup (replaces ROLE_PERSON_MAPPING) ──────────────────

    def find_by_role_keywords(self, text: str) -> list[str]:
        """
        'who works on frontend?' → query Employee.role, not a hardcoded dict.
        Returns canonical names of matching employees.
        """
        # Map common colloquial terms to searchable role/department keywords
        TERM_ALIASES = {
            'frontend': ['frontend', 'front-end', 'ui'],
            'front-end': ['frontend', 'front-end', 'ui'],
            'react': ['frontend', 'front-end', 'ui'],
            'ui': ['frontend', 'ui', 'design'],
            'backend': ['backend', 'back-end', 'server'],
            'back-end': ['backend', 'back-end', 'server'],
            'api': ['backend', 'back-end'],
            'devops': ['devops', 'infrastructure', 'deployment', 'ops'],
            'aws': ['devops', 'infrastructure', 'deployment', 'ops', 'cloud'],
            'cloud': ['devops', 'infrastructure', 'deployment', 'ops', 'cloud'],
            'deployment': ['devops', 'deployment', 'ops'],
            'fargate': ['devops', 'infrastructure', 'deployment'],
            'ecs': ['devops', 'infrastructure', 'deployment'],
            'ci/cd': ['devops', 'infrastructure', 'deployment'],
            'pipeline': ['devops', 'infrastructure', 'deployment'],
            'infrastructure': ['devops', 'infrastructure'],
            'qa': ['qa', 'quality', 'test'],
            'testing': ['qa', 'quality', 'test'],
            'database': ['database', 'data', 'db'],
            'postgresql': ['database', 'data', 'db'],
            'postgres': ['database', 'data', 'db'],
            'lead': ['lead', 'principal', 'senior', 'architect'],
        }

        text_lower = text.lower()
        search_terms = []
        for alias, expansions in TERM_ALIASES.items():
            if alias in text_lower:
                search_terms.extend(expansions)
        if not search_terms:
            search_terms = [text_lower]

        names = []
        for term in search_terms:
            for emp in self._employees:
                if (term in emp['role'].lower() or
                        term in emp['department'].lower()):
                    if emp['name'] not in names:
                        names.append(emp['name'])
        return names


# Module-level singleton — loaded once at import time
registry = PeopleRegistry()
