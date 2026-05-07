"""
Intent Classifier for Onboarding AI Chatbot (v4)

Replaces the rule-based keyword scorer with a single Groq LLM parse call.
The LLM reads the query and returns a structured retrieval plan (intent +
entities) in ~150 tokens. Previous turn context is included so follow-ups
("his commits", "give me more") resolve correctly.

Falls back to keyword rules if the LLM is unavailable (rate-limited, offline).
"""

import re
import sys
import os
import json
from typing import List, Tuple, Optional

from .types import (
    IntentType,
    ClassifiedIntent,
    TECH_TERMS,
)

# ── LLM parse helpers ────────────────────────────────────────────────────────

_INTENT_DESCRIPTIONS = [
    ('decision_query',       'why a tech/architecture decision was made, or asking about superseded/overridden decisions — "why React?", "rationale for JWT", "what decisions were superseded?", "which decisions were overridden?"'),
    ('person_query',         'what a person worked on, who worked on a topic, or who to contact — "Marcus\'s commits", "who did frontend?", "all commits by Marcus", "whom should I reach out for react help?"'),
    ('sprint_summary_query', 'sprint overview, team, or status — "sprint 2 summary", "who was in sprint 1", "what happened in sprint 3"'),
    ('timeline_query',       'when things happened, chronological history — "when was X decided?", "project timeline"'),
    ('howto_query',          'how to do something, setup guides, onboarding — "how to run locally", "new employee first steps"'),
    ('status_query',         'ticket or work item status — "status of ONBOARD-14", "what is open?", "is auth done?"'),
    ('ticket_query',         'details about a specific Jira ticket — "tell me about ONBOARD-14"'),
    ('meeting_query',        'what was discussed in a meeting — "sprint 1 planning meeting", "meeting minutes"'),
    ('conflict_query',       'conflicting or contradictory decisions — "any conflicts?", "does X conflict with Y?"'),
    ('provenance_query',     'where a decision came from — "trace JWT", "where did Tailwind come from?", "background behind SQLAlchemy"'),
    ('doc_drift_query',      'whether documentation is stale — "which docs are outdated?", "are docs current?", "doc drift"'),
    ('general_query',        'anything else'),
]

_PARSE_SYSTEM = (
    "You are a query parser for an engineering onboarding knowledge base. "
    "Return only valid JSON. No explanation, no markdown."
)

_DEFAULT_PEOPLE = (
    "Sarah Chen, Marcus Thompson, Lisa Park, "
    "Priya Sharma, James O'Brien, Dave Rossi"
)


def _build_parse_prompt(
    query: str,
    people_str: str,
    prev_context: Optional[str],
) -> str:
    intent_lines = "\n".join(f"  {k}: {v}" for k, v in _INTENT_DESCRIPTIONS)
    prev_line = f"\nPrevious turn: {prev_context}" if prev_context else ""
    return (
        f"Intents:\n{intent_lines}\n\n"
        f"Team members: {people_str}{prev_line}\n\n"
        f"Rules:\n"
        f"- Use person_query for ANY question about who did work, who to contact, or a named person's activity.\n"
        f"- Set the 'person' field ONLY if a name from the team list is explicitly in the query.\n"
        f"  Leave 'person' null for 'who should I contact' or 'who works on X' queries — the retriever will find them.\n"
        f"- Set topic to the main technology or concept (e.g. 'react', 'jwt', 'deployment').\n"
        f"- Set sprint only if a sprint number is mentioned.\n\n"
        f'Return ONLY this JSON:\n'
        f'{{\n'
        f'  "intent": "<intent name>",\n'
        f'  "person": "<full name from team list or null>",\n'
        f'  "topic": "<main tech or concept or null>",\n'
        f'  "sprint": "<number as string or null>",\n'
        f'  "ticket_id": "<ONBOARD-XX or null>",\n'
        f'  "confidence": <0.0-1.0>\n'
        f'}}\n\n'
        f"Query: {query}"
    )


def _parse_llm_json(raw: str) -> Optional[dict]:
    """Extract the JSON object from an LLM response, tolerating markdown fences."""
    raw = raw.strip()
    # Strip markdown fences if present
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _build_entities(parsed: dict, registry) -> List[str]:
    """Flatten LLM-returned structured fields into the entity list the retriever expects."""
    entities: List[str] = []
    seen: set = set()

    def add(val):
        if val and str(val).lower() not in seen:
            entities.append(str(val))
            seen.add(str(val).lower())

    # Ticket ID first (highest precision)
    ticket = parsed.get('ticket_id')
    if ticket and re.match(r'ONBOARD-\d+', str(ticket), re.IGNORECASE):
        add(ticket.upper())

    # Sprint number
    sprint = parsed.get('sprint')
    if sprint and str(sprint).strip().isdigit():
        add(str(sprint).strip())

    # Person — normalise to canonical name via registry
    person = parsed.get('person')
    if person:
        canonical = None
        if registry:
            try:
                canonical = registry.normalize_name(person)
            except Exception:
                pass
        add(canonical or person)

    # Topic
    topic = parsed.get('topic')
    if topic:
        add(str(topic).lower().strip())

    return entities


# ── Keyword-rule fallback (kept from v3, simplified) ─────────────────────────

def _keyword_classify(query: str, person_names: List[str], first_names: List[str], registry) -> ClassifiedIntent:  # noqa: ARG001
    """Rule-based fallback used when the LLM is unavailable."""
    ql = query.lower()
    entities = _rule_extract_entities(query, person_names, registry)

    # Hard patterns first
    if re.search(r'ONBOARD-\d+', query, re.IGNORECASE):
        ticket_ids = re.findall(r'ONBOARD-\d+', query, re.IGNORECASE)
        return ClassifiedIntent(IntentType.TICKET_QUERY, 0.95,
                                [t.upper() for t in ticket_ids], query)

    if any(p in ql for p in ['conflict', 'contradict', 'inconsisten', 'clash']):
        return ClassifiedIntent(IntentType.CONFLICT_QUERY, 0.88, entities, query)

    if any(p in ql for p in ['where did', 'come from', 'trace', 'provenance', 'background behind']):
        return ClassifiedIntent(IntentType.PROVENANCE_QUERY, 0.88, entities, query)

    if re.search(r'(doc|documentation).{0,20}(stale|outdated|current)|which docs|doc drift', ql):
        return ClassifiedIntent(IntentType.DOC_DRIFT_QUERY, 0.88, entities, query)

    if re.search(r'sprint\s*\d+', ql):
        return ClassifiedIntent(IntentType.SPRINT_SUMMARY_QUERY, 0.85, entities, query)

    # Person detection
    has_person = any(n in ql for n in person_names)
    who_role = re.search(
        r'who\s+(worked|did|made|wrote)|contact.*for\s+(frontend|backend)|who.{0,15}responsible',
        ql
    )
    if has_person or who_role:
        return ClassifiedIntent(IntentType.PERSON_QUERY, 0.82, entities, query)

    # Keyword scoring (condensed)
    _kw = {
        IntentType.DECISION_QUERY:  ['why', 'decision', 'chose', 'rationale', 'reason', 'switch'],
        IntentType.HOWTO_QUERY:     ['how', 'setup', 'install', 'guide', 'steps', 'first steps'],
        IntentType.STATUS_QUERY:    ['status', 'progress', 'done', 'open', 'blocked', 'complete'],
        IntentType.MEETING_QUERY:   ['meeting', 'standup', 'discussed', 'planning', 'retro'],
        IntentType.TIMELINE_QUERY:  ['when', 'timeline', 'history', 'date', 'recent', 'before'],
    }
    scores = {intent: sum(1 for kw in kws if kw in ql) for intent, kws in _kw.items()}
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        conf = min(0.5 + scores[best] * 0.1, 0.75)
        return ClassifiedIntent(best, conf, entities, query)

    return ClassifiedIntent(IntentType.GENERAL_QUERY, 0.3, entities, query)


def _rule_extract_entities(query: str, person_names: List[str], registry) -> List[str]:
    """Minimal entity extraction for the fallback path."""
    entities: List[str] = []
    ql = query.lower()
    seen: set = set()

    def add(val: str):
        if val.lower() not in seen:
            entities.append(val)
            seen.add(val.lower())

    for t in re.findall(r'ONBOARD-\d+', query, re.IGNORECASE):
        add(t.upper())
    for s in re.findall(r'[Ss]print\s*(\d+)', query):
        add(s)

    if registry:
        for variant in person_names:
            if variant in ql:
                canonical = registry.normalize_name(variant)
                if canonical:
                    add(canonical)
    for term in TECH_TERMS:
        if term in ql:
            add(term)

    return entities


# ── Main classifier ───────────────────────────────────────────────────────────

class IntentClassifier:
    """
    LLM-first intent classifier (v4).

    Calls Groq with a ~280-token prompt to parse intent + entities in one shot.
    Falls back to keyword rules if the LLM is unavailable.
    """

    def __init__(self):
        # Load person registry
        self._registry = None
        self._person_names: List[str] = []
        self._first_names: List[str] = []
        self._people_str: str = _DEFAULT_PEOPLE
        try:
            _chatbot_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if _chatbot_dir not in sys.path:
                sys.path.insert(0, _chatbot_dir)
            from retriever.people import registry
            self._registry = registry
            self._person_names = registry.name_variants_for_classifier()
            self._first_names = registry.get_all_first_names()
            all_names = registry.get_all_names()
            if all_names:
                self._people_str = ', '.join(all_names)
        except Exception:
            pass

        # Groq client for LLM parse
        self._llm_client = None
        self._llm_available = False
        try:
            from dotenv import load_dotenv
            _db_env = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                '..', 'database', '.env'
            )
            load_dotenv(os.path.normpath(_db_env))
            from openai import OpenAI
            key = os.getenv('GROQ_API_KEY')
            if key:
                self._llm_client = OpenAI(
                    api_key=key,
                    base_url='https://api.groq.com/openai/v1',
                )
                self._llm_available = True
        except Exception:
            pass

    def classify(self, query: str, prev_context: Optional[str] = None) -> ClassifiedIntent:
        """
        Classify a query into an intent + entities.

        prev_context: one-line summary of the previous turn, e.g.
            "person_query about Marcus Thompson"
        Used so the LLM understands follow-ups like "his commits" or "tell me more".
        """
        if self._llm_available:
            result = self._llm_parse(query, prev_context)
            if result is not None:
                return result

        # LLM unavailable or returned invalid JSON — use keyword rules
        return _keyword_classify(
            query, self._person_names, self._first_names, self._registry
        )

    def _llm_parse(self, query: str, prev_context: Optional[str]) -> Optional[ClassifiedIntent]:
        """Single Groq call → structured intent + entities."""
        try:
            prompt = _build_parse_prompt(query, self._people_str, prev_context)
            response = self._llm_client.chat.completions.create(
                model='llama-3.1-8b-instant',
                messages=[
                    {'role': 'system', 'content': _PARSE_SYSTEM},
                    {'role': 'user',   'content': prompt},
                ],
                temperature=0.1,
                max_tokens=120,
            )
            raw = response.choices[0].message.content
            parsed = _parse_llm_json(raw)
            if not parsed or 'intent' not in parsed:
                return None

            # Map intent string → IntentType
            intent_str = parsed.get('intent', 'general_query')
            try:
                intent_type = IntentType(intent_str)
            except ValueError:
                intent_type = IntentType.GENERAL_QUERY

            entities = _build_entities(parsed, self._registry)
            confidence = float(parsed.get('confidence', 0.85))

            return ClassifiedIntent(
                intent_type=intent_type,
                confidence=min(max(confidence, 0.0), 1.0),
                entities=entities,
                original_query=query,
            )
        except Exception:
            return None

    # ── Kept for classify_with_explanation (Streamlit debug view) ────────────

    def classify_with_explanation(self, query: str, prev_context: Optional[str] = None) -> Tuple[ClassifiedIntent, str]:
        result = self.classify(query, prev_context)
        used_llm = self._llm_available
        lines = [
            f"Query: {query}",
            f"Parser: {'LLM (llama-3.1-8b-instant)' if used_llm else 'keyword fallback'}",
            f"Intent: {result.intent_type.value}",
            f"Confidence: {result.confidence:.2f}",
            f"Entities: {result.entities}",
        ]
        return result, "\n".join(lines)


# ── Quick test ────────────────────────────────────────────────────────────────

def test_classifier():
    classifier = IntentClassifier()

    queries = [
        # These all failed with the old classifier
        ("get me all commits by Marcus",           "person_query"),
        ("get me all commits related to react",    "person_query"),
        ("new employee first steps",               "howto_query"),
        ("whom should I reach out for react doubts","person_query"),
        ("what are all key decisions about frontend","decision_query"),
        # Standard queries
        ("Why did we choose React?",               "decision_query"),
        ("What's the summary of Sprint 2?",        "sprint_summary_query"),
        ("Are there any conflicting decisions?",   "conflict_query"),
        ("Where did the JWT decision come from?",  "provenance_query"),
        ("Which docs are outdated?",               "doc_drift_query"),
        ("Tell me about ONBOARD-14",               "ticket_query"),
    ]

    print("=" * 70)
    print("INTENT CLASSIFIER TEST v4  (LLM parse)")
    print("=" * 70)
    for query, expected in queries:
        result = classifier.classify(query)
        ok = "✓" if result.intent_type.value == expected else "✗"
        print(f"\n  {ok} {query}")
        print(f"       intent={result.intent_type.value}  expected={expected}  conf={result.confidence:.2f}")
        print(f"       entities={result.entities}")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    test_classifier()
