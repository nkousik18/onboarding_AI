"""
Decision Extraction Script using DSPy-style + Bytez API

This script extracts decisions from all data sources:
- Meetings (key_decisions + raw transcript)
- Confluence pages (documented decisions)
- Jira tickets (decisions in comments)

And populates the unified `decisions` table.

Features:
- DSPy-style Signatures and ChainOfThought
- Deduplication based on title similarity
- Links duplicates via related_decisions field
- Detects superseded decisions (e.g., Material UI → Tailwind)
- Refined prompts to exclude task completions
- Extracts ALL fields: impact, rationale, alternatives, etc.

Usage:
    python scripts/extract_decisions.py --all
    python scripts/extract_decisions.py --meetings
    python scripts/extract_decisions.py --confluence
    python scripts/extract_decisions.py --jira
    python scripts/extract_decisions.py --dry-run
    python scripts/extract_decisions.py --all --skip-duplicates

Requirements:
    pip install bytez
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Any, Tuple
from difflib import SequenceMatcher

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False

# Add the parent directory to path for Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.db import transaction
from knowledge_base.models import Meeting, ConfluencePage, JiraTicket, GitCommit

# Import Decision model
try:
    from knowledge_base.models import Decision
except ImportError:
    print("ERROR: Decision model not found. Add it to knowledge_base/models.py first.")
    sys.exit(1)

# Bytez imports
from bytez import Bytez

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


# ============================================
# BYTEZ LLM BACKEND (DSPy-style)
# ============================================

BYTEZ_API_KEY = os.getenv('BYTEZ_API_KEY', '19408716817b70780ddaaea1a7e32eb6')


class BytezLM:
    """Bytez Language Model wrapper - DSPy-style interface."""
    
    def __init__(self, model_name: str = "openai/gpt-4o"):
        self.model_name = model_name
        self.sdk = Bytez(BYTEZ_API_KEY)
        self.model = self.sdk.model(model_name)
    
    def generate(self, prompt: str) -> str:
        """Generate a response from the LLM."""
        results = self.model.run([{"role": "user", "content": prompt}])
        
        if results.error:
            raise Exception(f"Bytez API error: {results.error}")
        
        return self._extract_text(results.output)
    
    def _extract_text(self, output: Any) -> str:
        """Extract text from response."""
        if isinstance(output, str):
            return output
        elif isinstance(output, dict):
            for key in ['choices', 'content', 'text', 'message']:
                if key in output:
                    val = output[key]
                    if key == 'choices':
                        return val[0]['message']['content']
                    elif isinstance(val, dict) and 'content' in val:
                        return val['content']
                    return str(val)
        elif isinstance(output, list) and output:
            return self._extract_text(output[0])
        return str(output)


# ============================================
# DSPy-STYLE SIGNATURES
# ============================================

@dataclass
class InputField:
    desc: str = ""

@dataclass
class OutputField:
    desc: str = ""


class Signature:
    """DSPy-style Signature base class."""
    
    @classmethod
    def get_input_fields(cls) -> dict:
        return {k: v for k, v in cls.__dict__.items() if isinstance(v, InputField)}
    
    @classmethod
    def get_output_fields(cls) -> dict:
        return {k: v for k, v in cls.__dict__.items() if isinstance(v, OutputField)}


class ExtractDecisionsFromMeeting(Signature):
    """Extract all DECISIONS (not tasks or action items) made during a meeting."""
    
    transcript = InputField(desc="Meeting transcript")
    meeting_title = InputField(desc="Title of the meeting")
    meeting_date = InputField(desc="Date of the meeting")
    participants = InputField(desc="Meeting participants")
    
    decisions = OutputField(desc="JSON array of decision objects")


class ExtractDecisionsFromConfluence(Signature):
    """Extract DECISIONS documented in a Confluence page."""
    
    content = InputField(desc="Page content in markdown")
    title = InputField(desc="Page title")
    author = InputField(desc="Page author")
    page_date = InputField(desc="Page creation/update date")
    
    decisions = OutputField(desc="JSON array of decision objects")


class ExtractDecisionsFromJira(Signature):
    """Extract DECISIONS (not task completions) from Jira ticket discussions."""
    
    ticket_key = InputField(desc="Jira ticket key")
    summary = InputField(desc="Ticket summary")
    description = InputField(desc="Ticket description")
    comments = InputField(desc="Ticket comments")
    
    decisions = OutputField(desc="JSON array of decision objects")


# ============================================
# DSPy-STYLE MODULES
# ============================================

@dataclass
class Prediction:
    """DSPy-style prediction result."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class ChainOfThought:
    """DSPy-style ChainOfThought module with refined prompts."""
    
    def __init__(self, signature: type):
        self.signature = signature
    
    def forward(self, lm: BytezLM, source_type: str = "meeting", **kwargs) -> Prediction:
        prompt = self._build_prompt(source_type, **kwargs)
        response = lm.generate(prompt)
        outputs = self._parse_response(response)
        return Prediction(**outputs)
    
    def _build_prompt(self, source_type: str, **kwargs) -> str:
        parts = [
            f"Task: {self.signature.__doc__}",
            "",
            "=" * 50,
            "CRITICAL: WHAT IS A DECISION vs WHAT IS NOT",
            "=" * 50,
            "",
            "A DECISION is a CHOICE made between alternatives that affects how the project proceeds.",
            "",
            "✅ THESE ARE DECISIONS (extract these):",
            "  - 'We decided to use React instead of Vue' → Choice between alternatives",
            "  - 'We chose JWT over session-based auth' → Choice with reasoning",
            "  - 'We will switch from Material UI to Tailwind' → Change in direction (SUPERSEDES previous)",
            "  - 'Managers will see all employees, not just direct reports' → Design choice",
            "  - 'We'll use PostgreSQL for the database' → Technology choice",
            "",
            "❌ THESE ARE NOT DECISIONS (DO NOT extract these):",
            "  - 'Login page is done' → Task completion",
            "  - 'Marcus will set up the project' → Action item/assignment",
            "  - 'Tests are passing' → Status update",
            "  - 'I'll have it ready by Friday' → Commitment/deadline",
            "  - 'PR is up for review' → Status update",
            "  - 'Fixed the bug in authentication' → Bug fix (not a decision)",
            "  - 'Added unit tests' → Task completion",
            "  - 'Component is ready' → Status update",
            "",
            "=" * 50,
            "INPUTS:",
            "=" * 50,
        ]
        
        for name, field in self.signature.get_input_fields().items():
            value = kwargs.get(name, "")
            if name in ['transcript', 'content', 'description', 'comments']:
                value = str(value)[:10000]
            parts.append(f"\n{name.upper()}:\n{value}")
        
        parts.extend([
            "",
            "=" * 50,
            "ANALYSIS STEPS:",
            "=" * 50,
            "",
            "Think step by step:",
            "1. Read through the content carefully",
            "2. Look for statements where a CHOICE was made between alternatives",
            "3. For each choice, extract WHY it was made (the rationale)",
            "4. Identify the IMPACT of the decision (what does it affect?)",
            "5. Check if this decision SUPERSEDES a previous decision (e.g., 'switch from X to Y')",
            "6. SKIP any task completions, status updates, bug fixes, or action items",
            "7. Categorize each decision (architecture/technology/process/design/infrastructure/security)",
            "",
            "=" * 50,
            "OUTPUT FORMAT:",
            "=" * 50,
            "",
            "Return a JSON array of decisions. Each decision MUST have ALL these fields:",
            """```json
[
  {
    "title": "Short decision title - what was chosen (e.g., 'Use React for frontend')",
    "description": "Detailed description of the decision",
    "rationale": "WHY this was decided - the reasoning behind the choice",
    "alternatives_considered": "Other options that were discussed or rejected (e.g., 'Vue, Angular')",
    "impact": "What this decision affects (e.g., 'Frontend architecture, developer hiring, training')",
    "category": "architecture|technology|process|design|infrastructure|security",
    "decided_by": ["Person 1", "Person 2"],
    "related_tickets": ["ONBOARD-11"],
    "supersedes_decision": "Previous decision this replaces, if any (e.g., 'Use Material UI') or null",
    "tags": ["frontend", "framework"],
    "confidence": 0.9
  }
]
```""",
            "",
            "RULES:",
            "- ONLY include TRUE decisions (choices between alternatives)",
            "- Do NOT include task completions or status updates",
            "- Do NOT include action items or assignments",
            "- Do NOT include bug fixes or implementations",
            "- ALWAYS include impact - what does this decision affect?",
            "- Check for superseded decisions (e.g., 'switch from X to Y' supersedes 'use X')",
            "- If no decisions were found, return: []",
            "- Confidence should be 0.7-1.0 based on how clear the decision was",
            "",
            "JSON array of decisions:"
        ])
        
        return "\n".join(parts)
    
    def _parse_response(self, response: str) -> dict:
        """Parse LLM response to extract decisions."""
        decisions = []
        
        # Clean response
        response = response.strip()
        response = re.sub(r'^```json\s*', '', response)
        response = re.sub(r'^```\s*', '', response)
        response = re.sub(r'\s*```$', '', response)
        
        # Find JSON array
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            try:
                decisions = json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        
        return {'decisions': decisions}


# ============================================
# DEDUPLICATION & SUPERSESSION LOGIC
# ============================================

class DecisionDeduplicator:
    """
    Handles deduplication and supersession detection.
    Uses semantic embeddings (sentence-transformers/all-MiniLM-L6-v2) for similarity.
    Falls back to SequenceMatcher string similarity if package not installed.
    """

    EMBEDDING_MODEL = 'all-MiniLM-L6-v2'

    def __init__(self, similarity_threshold: float = 0.70):
        self.similarity_threshold = similarity_threshold
        self.existing_decisions = []  # List of (id, title, source_type, status) tuples
        self._model = None
        self._embedding_cache = {}  # normalized_title -> np.ndarray

    def _get_model(self):
        if self._model is None:
            if EMBEDDINGS_AVAILABLE:
                print(f"  Loading embedding model ({self.EMBEDDING_MODEL})...")
                self._model = SentenceTransformer(self.EMBEDDING_MODEL)
                print("  Embedding model ready")
            else:
                print("  WARNING: sentence-transformers not installed. Falling back to string matching.")
                print("  Run: pip install sentence-transformers")
        return self._model

    def _get_embedding(self, text: str):
        """Embed text, caching to avoid recomputation."""
        if text not in self._embedding_cache:
            model = self._get_model()
            if model is not None:
                self._embedding_cache[text] = model.encode(text, normalize_embeddings=True)
            else:
                self._embedding_cache[text] = None
        return self._embedding_cache[text]

    def normalize_title(self, title: str) -> str:
        """Strip action prefixes so 'use React' and 'adopt React' embed similarly."""
        title = title.lower().strip()
        prefixes = [
            'use ', 'adopt ', 'implement ', 'choose ', 'select ',
            'switch to ', 'decided to ', 'decision to ', 'chose ',
            'switched to ', 'selected ', 'adopted ', 'switch from '
        ]
        for prefix in prefixes:
            if title.startswith(prefix):
                title = title[len(prefix):]
        return title

    def calculate_similarity(self, title1: str, title2: str) -> float:
        """Cosine similarity on embeddings. Falls back to SequenceMatcher ratio."""
        t1 = self.normalize_title(title1)
        t2 = self.normalize_title(title2)

        emb1 = self._get_embedding(t1)
        emb2 = self._get_embedding(t2)

        if emb1 is not None and emb2 is not None:
            # Embeddings are L2-normalized, so dot product == cosine similarity
            return float(np.dot(emb1, emb2))

        return SequenceMatcher(None, t1, t2).ratio()

    def load_existing_decisions(self):
        """Load existing decisions and pre-warm embedding cache."""
        self.existing_decisions = [
            (str(d.id), d.title.lower().strip(), d.source_type, d.status)
            for d in Decision.objects.all()
        ]

        if EMBEDDINGS_AVAILABLE and self.existing_decisions:
            self._get_model()  # load once upfront
            for _, title, _, _ in self.existing_decisions:
                self._get_embedding(self.normalize_title(title))

        print(f"  Loaded {len(self.existing_decisions)} existing decisions for dedup")

    def find_duplicates(self, new_title: str) -> List[str]:
        """Find existing decisions semantically similar to the new one."""
        duplicates = []
        for existing_id, existing_title, *_ in self.existing_decisions:
            similarity = self.calculate_similarity(new_title, existing_title)
            if similarity >= self.similarity_threshold:
                duplicates.append(existing_id)
        return duplicates

    def is_duplicate(self, new_title: str) -> Tuple[bool, List[str]]:
        """Check if a decision is a duplicate."""
        duplicates = self.find_duplicates(new_title)
        return (len(duplicates) > 0, duplicates)

    def find_superseded_decision(self, supersedes_text: str) -> Optional[str]:
        """Find the existing decision most semantically similar to supersedes_text."""
        if not supersedes_text or supersedes_text.lower() in ['null', 'none', 'n/a', '']:
            return None

        best_match_id = None
        best_similarity = 0.0

        for existing_id, existing_title, *_ in self.existing_decisions:
            similarity = self.calculate_similarity(supersedes_text, existing_title)
            if similarity > best_similarity and similarity >= 0.6:
                best_similarity = similarity
                best_match_id = existing_id

        return best_match_id

    def add_decision(self, decision_id: str, title: str, source_type: str, status: str = 'active'):
        """Add a new decision to the tracking list and warm its embedding cache."""
        self.existing_decisions.append((decision_id, title.lower().strip(), source_type, status))
        self._get_embedding(self.normalize_title(title.lower().strip()))


# ============================================
# DECISION EXTRACTOR (DSPy-style Pipeline)
# ============================================

class DecisionExtractor:
    """DSPy-style module for extracting decisions from all sources."""
    
    def __init__(self, lm: BytezLM, deduplicator: DecisionDeduplicator):
        self.lm = lm
        self.deduplicator = deduplicator
        
        # Sub-modules for each source type
        self.meeting_extractor = ChainOfThought(ExtractDecisionsFromMeeting)
        self.confluence_extractor = ChainOfThought(ExtractDecisionsFromConfluence)
        self.jira_extractor = ChainOfThought(ExtractDecisionsFromJira)
    
    def extract_from_meeting(self, meeting: Meeting) -> List[dict]:
        """Extract decisions from a meeting."""
        
        participants = ""
        if meeting.participants:
            try:
                p = json.loads(meeting.participants)
                participants = ", ".join(p) if isinstance(p, list) else meeting.participants
            except:
                participants = meeting.participants
        
        result = self.meeting_extractor.forward(
            self.lm,
            source_type="meeting",
            transcript=meeting.raw_vtt_content,
            meeting_title=meeting.title or "Team Meeting",
            meeting_date=str(meeting.meeting_date) if meeting.meeting_date else "Unknown",
            participants=participants
        )
        
        decisions = result.decisions if hasattr(result, 'decisions') else []
        
        # Enrich with source info
        enriched = []
        for d in decisions:
            d['source_type'] = 'meeting'
            d['source_id'] = str(meeting.id)
            d['source_title'] = meeting.title
            d['decision_date'] = meeting.meeting_date.date() if meeting.meeting_date else None
            d['extraction_notes'] = f"Extracted from meeting: {meeting.title}"
            
            # Check for duplicates
            is_dup, related_ids = self.deduplicator.is_duplicate(d.get('title', ''))
            d['is_duplicate'] = is_dup
            d['related_decisions'] = related_ids
            
            # Check for superseded decision
            supersedes_text = d.get('supersedes_decision')
            if supersedes_text:
                superseded_id = self.deduplicator.find_superseded_decision(supersedes_text)
                d['supersedes_id'] = superseded_id
            else:
                d['supersedes_id'] = None
            
            enriched.append(d)
        
        return enriched
    
    def extract_from_confluence(self, page: ConfluencePage) -> List[dict]:
        """Extract decisions from a Confluence page."""
        
        result = self.confluence_extractor.forward(
            self.lm,
            source_type="confluence",
            content=page.content,
            title=page.title,
            author=page.author or "Unknown",
            page_date=str(page.page_created_date) if page.page_created_date else "Unknown"
        )
        
        decisions = result.decisions if hasattr(result, 'decisions') else []
        
        enriched = []
        for d in decisions:
            d['source_type'] = 'confluence'
            d['source_id'] = str(page.id)
            d['source_title'] = page.title
            d['decision_date'] = page.page_created_date.date() if page.page_created_date else None
            d['extraction_notes'] = f"Extracted from Confluence page: {page.title}"
            
            is_dup, related_ids = self.deduplicator.is_duplicate(d.get('title', ''))
            d['is_duplicate'] = is_dup
            d['related_decisions'] = related_ids
            
            supersedes_text = d.get('supersedes_decision')
            if supersedes_text:
                superseded_id = self.deduplicator.find_superseded_decision(supersedes_text)
                d['supersedes_id'] = superseded_id
            else:
                d['supersedes_id'] = None
            
            enriched.append(d)
        
        return enriched
    
    def extract_from_jira(self, ticket: JiraTicket) -> List[dict]:
        """Extract decisions from a Jira ticket."""
        
        result = self.jira_extractor.forward(
            self.lm,
            source_type="jira",
            ticket_key=ticket.issue_key,
            summary=ticket.summary,
            description=ticket.description or "",
            comments=ticket.comments or ""
        )
        
        decisions = result.decisions if hasattr(result, 'decisions') else []
        
        enriched = []
        for d in decisions:
            d['source_type'] = 'jira'
            d['source_id'] = str(ticket.id)
            d['source_title'] = f"{ticket.issue_key}: {ticket.summary}"
            d['decision_date'] = ticket.created_date.date() if ticket.created_date else None
            d['extraction_notes'] = f"Extracted from Jira ticket: {ticket.issue_key}"
            
            # Always include this ticket
            if 'related_tickets' not in d or not d['related_tickets']:
                d['related_tickets'] = [ticket.issue_key]
            elif ticket.issue_key not in d['related_tickets']:
                d['related_tickets'].append(ticket.issue_key)
            
            is_dup, related_ids = self.deduplicator.is_duplicate(d.get('title', ''))
            d['is_duplicate'] = is_dup
            d['related_decisions'] = related_ids
            
            supersedes_text = d.get('supersedes_decision')
            if supersedes_text:
                superseded_id = self.deduplicator.find_superseded_decision(supersedes_text)
                d['supersedes_id'] = superseded_id
            else:
                d['supersedes_id'] = None
            
            enriched.append(d)
        
        return enriched


# ============================================
# DATABASE OPERATIONS
# ============================================

def save_decision(decision_data: dict, deduplicator: DecisionDeduplicator) -> Optional[Decision]:
    """Save a decision to the database with ALL fields."""
    
    try:
        import uuid as uuid_lib
        
        # Parse decision_date
        decision_date = decision_data.get('decision_date')
        if isinstance(decision_date, str):
            decision_date = datetime.strptime(decision_date, '%Y-%m-%d').date()
        
        if not decision_date:
            print(f"    Skipping (no date): {decision_data.get('title', '?')[:30]}")
            return None
        
        # Parse source_id
        source_id = decision_data.get('source_id')
        if source_id:
            source_id = uuid_lib.UUID(source_id)
        
        # Parse related_decisions
        related_decisions = decision_data.get('related_decisions', [])
        if related_decisions:
            related_decisions = [
                uuid_lib.UUID(rid) if isinstance(rid, str) else rid 
                for rid in related_decisions
            ]
        
        # Parse supersedes_id
        supersedes_id = decision_data.get('supersedes_id')
        supersedes_obj = None
        if supersedes_id:
            try:
                supersedes_obj = Decision.objects.get(id=uuid_lib.UUID(supersedes_id))
            except Decision.DoesNotExist:
                supersedes_obj = None
        
        # Create the decision
        decision = Decision.objects.create(
            # Core info
            title=decision_data.get('title', 'Unknown Decision')[:500],
            description=decision_data.get('description'),
            decision_date=decision_date,
            
            # Context and reasoning
            rationale=decision_data.get('rationale'),
            alternatives_considered=decision_data.get('alternatives_considered'),
            impact=decision_data.get('impact'),
            
            # People
            decided_by=decision_data.get('decided_by'),
            
            # Source tracking
            source_type=decision_data.get('source_type'),
            source_id=source_id,
            source_title=decision_data.get('source_title'),
            
            # Relationships
            related_tickets=decision_data.get('related_tickets'),
            related_decisions=related_decisions if related_decisions else None,
            
            # Categorization
            category=decision_data.get('category'),
            tags=decision_data.get('tags'),
            
            # Lifecycle
            status='active',
            supersedes=supersedes_obj,
            
            # Metadata
            confidence_score=decision_data.get('confidence'),
            extraction_notes=decision_data.get('extraction_notes'),
        )
        
        # Update the superseded decision
        if supersedes_obj:
            supersedes_obj.superseded_by = decision
            supersedes_obj.status = 'superseded'
            supersedes_obj.save()
            print(f"    ↳ Supersedes: {supersedes_obj.title[:40]}")
        
        # Add to deduplicator
        deduplicator.add_decision(str(decision.id), decision.title, decision.source_type)
        
        return decision
        
    except Exception as e:
        print(f"    Error saving: {e}")
        import traceback
        traceback.print_exc()
        return None


def update_related_decisions(decision: Decision, related_ids: List[str]):
    """Update related decisions to link back."""
    if not related_ids:
        return
    
    try:
        import uuid as uuid_lib
        for rid in related_ids:
            try:
                related = Decision.objects.get(id=uuid_lib.UUID(rid))
                current = related.related_decisions or []
                if str(decision.id) not in [str(r) for r in current]:
                    current.append(decision.id)
                    related.related_decisions = current
                    related.save()
            except Decision.DoesNotExist:
                pass
    except Exception as e:
        print(f"    Error updating related: {e}")


# ============================================
# CLI
# ============================================

def main():
    parser = argparse.ArgumentParser(description='Extract decisions using DSPy + Bytez')
    parser.add_argument('--all', action='store_true', help='Process all sources')
    parser.add_argument('--meetings', action='store_true', help='Process meetings only')
    parser.add_argument('--confluence', action='store_true', help='Process Confluence only')
    parser.add_argument('--jira', action='store_true', help='Process Jira only')
    parser.add_argument('--model', type=str, default='openai/gpt-4o', help='Model to use')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
    parser.add_argument('--clear', action='store_true', help='Clear existing decisions first')
    parser.add_argument('--skip-duplicates', action='store_true', help='Skip duplicate decisions')
    parser.add_argument('--similarity', type=float, default=0.70, help='Similarity threshold (0-1)')
    
    args = parser.parse_args()
    
    if not any([args.all, args.meetings, args.confluence, args.jira]):
        args.all = True
    
    print("=" * 60)
    print("DSPy-Style Decision Extractor with Bytez Backend")
    print("=" * 60)
    print(f"\nSettings:")
    print(f"  API Key: {BYTEZ_API_KEY[:10]}...")
    print(f"  Model: {args.model}")
    print(f"  Similarity Threshold: {args.similarity}")
    print(f"  Skip Duplicates: {args.skip_duplicates}")
    
    # Initialize
    lm = BytezLM(model_name=args.model)
    deduplicator = DecisionDeduplicator(similarity_threshold=args.similarity)
    extractor = DecisionExtractor(lm=lm, deduplicator=deduplicator)
    
    print(f"\nDSPy Modules:")
    print(f"  - ChainOfThought(ExtractDecisionsFromMeeting)")
    print(f"  - ChainOfThought(ExtractDecisionsFromConfluence)")
    print(f"  - ChainOfThought(ExtractDecisionsFromJira)")
    print(f"  - DecisionDeduplicator (threshold: {args.similarity})")
    
    print(f"\nFields extracted by LLM:")
    print(f"  - title, description, rationale, alternatives_considered")
    print(f"  - impact, category, decided_by, related_tickets")
    print(f"  - supersedes_decision, tags, confidence")
    
    # Clear or load existing
    if args.clear and not args.dry_run:
        print(f"\nClearing existing decisions...")
        count = Decision.objects.count()
        Decision.objects.all().delete()
        print(f"  Deleted {count} decisions")
    else:
        print(f"\nLoading existing decisions...")
        deduplicator.load_existing_decisions()
    
    stats = {'found': 0, 'saved': 0, 'duplicates': 0, 'skipped': 0, 'superseded': 0}
    
    # Process Meetings (PRIMARY SOURCE)
    if args.all or args.meetings:
        print(f"\n{'='*60}")
        print("PROCESSING MEETINGS (Primary source)")
        print(f"{'='*60}")
        
        meetings = Meeting.objects.all()
        print(f"Found {meetings.count()} meetings")
        
        for meeting in meetings:
            print(f"\n→ {meeting.title}")
            
            try:
                decisions = extractor.extract_from_meeting(meeting)
                print(f"  Extracted {len(decisions)} decisions")
                
                for d in decisions:
                    stats['found'] += 1
                    is_dup = d.get('is_duplicate', False)
                    has_supersedes = d.get('supersedes_id') is not None
                    
                    markers = []
                    if is_dup:
                        markers.append("DUP")
                    if has_supersedes:
                        markers.append("SUPERSEDES")
                    marker_str = f" [{', '.join(markers)}]" if markers else ""
                    
                    print(f"    • {d.get('title', '?')[:50]}{marker_str}")
                    
                    if is_dup:
                        stats['duplicates'] += 1
                        if args.skip_duplicates:
                            stats['skipped'] += 1
                            continue
                    
                    if not args.dry_run:
                        saved = save_decision(d, deduplicator)
                        if saved:
                            stats['saved'] += 1
                            if has_supersedes:
                                stats['superseded'] += 1
                            if d.get('related_decisions'):
                                update_related_decisions(saved, d['related_decisions'])
                            
            except Exception as e:
                print(f"  Error: {e}")
                import traceback
                traceback.print_exc()
    
    # Process Confluence (SECONDARY)
    if args.all or args.confluence:
        print(f"\n{'='*60}")
        print("PROCESSING CONFLUENCE (Secondary source)")
        print(f"{'='*60}")
        
        pages = ConfluencePage.objects.all()
        print(f"Found {pages.count()} pages")
        
        for page in pages:
            print(f"\n→ {page.title}")
            
            try:
                decisions = extractor.extract_from_confluence(page)
                print(f"  Extracted {len(decisions)} decisions")
                
                for d in decisions:
                    stats['found'] += 1
                    is_dup = d.get('is_duplicate', False)
                    has_supersedes = d.get('supersedes_id') is not None
                    
                    markers = []
                    if is_dup:
                        markers.append("DUP")
                    if has_supersedes:
                        markers.append("SUPERSEDES")
                    marker_str = f" [{', '.join(markers)}]" if markers else ""
                    
                    print(f"    • {d.get('title', '?')[:50]}{marker_str}")
                    
                    if is_dup:
                        stats['duplicates'] += 1
                        if args.skip_duplicates:
                            stats['skipped'] += 1
                            continue
                    
                    if not args.dry_run:
                        saved = save_decision(d, deduplicator)
                        if saved:
                            stats['saved'] += 1
                            if has_supersedes:
                                stats['superseded'] += 1
                            if d.get('related_decisions'):
                                update_related_decisions(saved, d['related_decisions'])
                            
            except Exception as e:
                print(f"  Error: {e}")
    
    # Process Jira (TERTIARY)
    if args.all or args.jira:
        print(f"\n{'='*60}")
        print("PROCESSING JIRA (Tertiary - decisions in discussions)")
        print(f"{'='*60}")
        
        tickets = JiraTicket.objects.exclude(comments__isnull=True).exclude(comments='')
        print(f"Found {tickets.count()} tickets with comments")
        
        for ticket in tickets:
            print(f"\n→ {ticket.issue_key}: {ticket.summary[:35]}")
            
            try:
                decisions = extractor.extract_from_jira(ticket)
                print(f"  Extracted {len(decisions)} decisions")
                
                for d in decisions:
                    stats['found'] += 1
                    is_dup = d.get('is_duplicate', False)
                    has_supersedes = d.get('supersedes_id') is not None
                    
                    markers = []
                    if is_dup:
                        markers.append("DUP")
                    if has_supersedes:
                        markers.append("SUPERSEDES")
                    marker_str = f" [{', '.join(markers)}]" if markers else ""
                    
                    print(f"    • {d.get('title', '?')[:50]}{marker_str}")
                    
                    if is_dup:
                        stats['duplicates'] += 1
                        if args.skip_duplicates:
                            stats['skipped'] += 1
                            continue
                    
                    if not args.dry_run:
                        saved = save_decision(d, deduplicator)
                        if saved:
                            stats['saved'] += 1
                            if has_supersedes:
                                stats['superseded'] += 1
                            if d.get('related_decisions'):
                                update_related_decisions(saved, d['related_decisions'])
                            
            except Exception as e:
                print(f"  Error: {e}")
    
    # Summary
    print(f"\n{'='*60}")
    print("COMPLETE")
    print(f"{'='*60}")
    print(f"  Total found:        {stats['found']}")
    print(f"  Duplicates:         {stats['duplicates']}")
    print(f"  Superseded links:   {stats['superseded']}")
    
    if args.dry_run:
        print(f"  [DRY RUN] Would save: {stats['found'] - stats['skipped']}")
        print(f"  [DRY RUN] Would skip: {stats['skipped']}")
    else:
        print(f"  Saved:              {stats['saved']}")
        print(f"  Skipped:            {stats['skipped']}")
    
    # Timeline preview
    if not args.dry_run and stats['saved'] > 0:
        print(f"\n{'='*60}")
        print("DECISION TIMELINE PREVIEW")
        print(f"{'='*60}")
        
        decisions = Decision.objects.order_by('decision_date')[:15]
        for d in decisions:
            cat = (d.category or 'N/A')[:10]
            src = d.source_type[:8]
            status = d.status[:6]
            print(f"  {d.decision_date} | {cat:10} | {src:8} | {status:6} | {d.title[:30]}")
        
        print(f"\n  Total decisions: {Decision.objects.count()}")
        print(f"  Active: {Decision.objects.filter(status='active').count()}")
        print(f"  Superseded: {Decision.objects.filter(status='superseded').count()}")
        
        # Show supersession chains
        superseded = Decision.objects.filter(status='superseded')
        if superseded.exists():
            print(f"\n  Supersession chains:")
            for d in superseded[:5]:
                if d.superseded_by:
                    print(f"    {d.title[:30]} → {d.superseded_by.title[:30]}")


if __name__ == '__main__':
    main()