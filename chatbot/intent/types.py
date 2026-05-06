"""
Intent Types and Configurations for Onboarding AI Chatbot

Defines all possible intent types and their associated keywords,
target tables, and example queries.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict


class IntentType(Enum):
    """All possible intent types for user queries."""
    
    DECISION_QUERY = "decision_query"
    PERSON_QUERY = "person_query"
    TIMELINE_QUERY = "timeline_query"
    HOWTO_QUERY = "howto_query"
    STATUS_QUERY = "status_query"
    TICKET_QUERY = "ticket_query"
    MEETING_QUERY = "meeting_query"
    SPRINT_SUMMARY_QUERY = "sprint_summary_query"
    CONFLICT_QUERY = "conflict_query"
    PROVENANCE_QUERY = "provenance_query"
    DOC_DRIFT_QUERY = "doc_drift_query"
    GENERAL_QUERY = "general_query"


@dataclass
class IntentConfig:
    """Configuration for an intent type."""
    
    intent_type: IntentType
    keywords: List[str]
    tables: List[str]
    description: str
    example_queries: List[str] = field(default_factory=list)


# Intent configurations with keywords and target tables
INTENT_CONFIGS: Dict[IntentType, IntentConfig] = {
    
    IntentType.DECISION_QUERY: IntentConfig(
        intent_type=IntentType.DECISION_QUERY,
        keywords=[
            'why', 'decision', 'decided', 'chose', 'choose', 'chosen',
            'rationale', 'reasoning', 'reason', 'switch', 'switched',
            'alternative', 'alternatives', 'instead', 'over',
            'approach', 'strategy', 'picked', 'selected', 'preference'
        ],
        tables=['decisions', 'meetings'],
        description="Questions about why decisions were made",
        example_queries=[
            "Why did we choose React?",
            "What was the decision on authentication?",
            "Why did we switch from Material UI to Tailwind?",
        ]
    ),
    
    IntentType.PERSON_QUERY: IntentConfig(
        intent_type=IntentType.PERSON_QUERY,
        keywords=[
            'who', 'worked', 'assigned', 'responsible', 'owner',
            'contributor', 'team', 'member', 'developer', 'engineer',
            'authored', 'created', 'built', 'wrote', 'implemented'
        ],
        tables=['employees', 'jira_tickets', 'git_commits', 'decisions'],
        description="Questions about who did what",
        example_queries=[
            "Who worked on authentication?",
            "What has Marcus been working on?",
            "Who is assigned to ONBOARD-14?",
        ]
    ),
    
    IntentType.TIMELINE_QUERY: IntentConfig(
        intent_type=IntentType.TIMELINE_QUERY,
        keywords=[
            'when', 'timeline', 'history', 'chronological', 'order',
            'sequence', 'happened', 'occurred', 'date', 'time',
            'before', 'after', 'first', 'last', 'recent', 'earlier'
        ],
        tables=['decisions', 'meetings', 'jira_tickets', 'git_commits'],
        description="Questions about when things happened",
        example_queries=[
            "What happened in Sprint 1?",
            "When was the authentication decision made?",
            "Show me the project timeline",
        ]
    ),
    
    IntentType.HOWTO_QUERY: IntentConfig(
        intent_type=IntentType.HOWTO_QUERY,
        keywords=[
            'how', 'setup', 'set up', 'configure', 'install', 'run',
            'start', 'guide', 'tutorial', 'steps', 'instructions',
            'documentation', 'docs', 'help', 'getting started',
            'prerequisite', 'requirements', 'environment'
        ],
        tables=['confluence_pages'],
        description="Questions about how to do something",
        example_queries=[
            "How do I set up the project?",
            "What are the prerequisites?",
            "How do I run the tests?",
        ]
    ),
    
    IntentType.STATUS_QUERY: IntentConfig(
        intent_type=IntentType.STATUS_QUERY,
        keywords=[
            'status', 'progress', 'state', 'current', 'now',
            'done', 'complete', 'finished', 'pending', 'open',
            'blocked', 'blocker', 'in progress', 'todo', 'remaining'
        ],
        tables=['jira_tickets'],
        description="Questions about current status",
        example_queries=[
            "What's the status of ONBOARD-15?",
            "What tickets are still open?",
            "Is the authentication work done?",
        ]
    ),
    
    IntentType.TICKET_QUERY: IntentConfig(
        intent_type=IntentType.TICKET_QUERY,
        keywords=[
            'ticket', 'issue', 'jira', 'task', 'story', 'bug',
            'feature', 'onboard-', 'epic', 'subtask'
        ],
        tables=['jira_tickets', 'git_commits', 'decisions', 'entity_references'],
        description="Questions about specific tickets",
        example_queries=[
            "Tell me about ONBOARD-14",
            "What's the description of ONBOARD-15?",
            "What commits are related to ONBOARD-14?",
        ]
    ),
    
    IntentType.MEETING_QUERY: IntentConfig(
        intent_type=IntentType.MEETING_QUERY,
        keywords=[
            'meeting', 'meetings', 'discussed', 'discussion', 'talked',
            'standup', 'planning', 'retrospective', 'retro', 'review',
            'sync', 'session', 'call', 'agenda', 'minutes'
        ],
        tables=['meetings'],
        description="Questions about meetings",
        example_queries=[
            "What was discussed in Sprint 1 planning?",
            "Summarize the last meeting",
            "What were the action items from the standup?",
        ]
    ),
    
    # NEW: Sprint Summary Query
    IntentType.SPRINT_SUMMARY_QUERY: IntentConfig(
        intent_type=IntentType.SPRINT_SUMMARY_QUERY,
        keywords=[
            'sprint summary', 'sprint overview', 'summarize sprint',
            'summary of sprint', 'overview of sprint', 'sprint report',
            'sprint highlights', 'sprint accomplishments', 'sprint review',
            'what happened in sprint', 'sprint progress', 'sprint recap',
            'sprint insights', 'sprint analysis', 'sprint breakdown'
        ],
        tables=['sprints', 'sprint_tickets', 'jira_tickets', 'decisions', 'meetings', 'git_commits'],
        description="Questions asking for a complete sprint summary/overview",
        example_queries=[
            "What's the summary of Sprint 1?",
            "Give me an overview of Sprint 2",
            "Summarize what happened in Sprint 1",
            "What were the highlights of Sprint 1?",
            "Sprint 1 recap",
        ]
    ),
    
    IntentType.CONFLICT_QUERY: IntentConfig(
        intent_type=IntentType.CONFLICT_QUERY,
        keywords=[
            'conflict', 'conflicts', 'conflicting', 'contradict', 'contradicts',
            'contradiction', 'inconsistent', 'inconsistency', 'clash', 'clashes',
            'incompatible', 'opposing', 'tension', 'contradictory',
        ],
        tables=['decision_conflicts', 'decisions'],
        description="Questions about conflicting architectural decisions",
        example_queries=[
            "Are there any conflicting decisions?",
            "What decisions contradict each other?",
            "Does using SQLAlchemy conflict with anything?",
            "Show me architectural conflicts",
        ]
    ),

    IntentType.PROVENANCE_QUERY: IntentConfig(
        intent_type=IntentType.PROVENANCE_QUERY,
        keywords=[
            'provenance', 'where did', 'come from', 'origin', 'history of',
            'trace', 'tracing', 'background', 'led to', 'resulted in',
            'what happened after', 'commits after', 'full history',
            'how did we get', 'evidence', 'source of',
        ],
        tables=['decisions', 'entity_references', 'git_commits', 'jira_tickets'],
        description="Questions tracing the origin and impact of a decision",
        example_queries=[
            "Where did the decision to use JWT come from?",
            "Show me the history behind the Tailwind CSS switch",
            "What commits followed the JWT decision?",
            "Trace the SQLAlchemy decision",
        ]
    ),

    IntentType.DOC_DRIFT_QUERY: IntentConfig(
        intent_type=IntentType.DOC_DRIFT_QUERY,
        keywords=[
            'outdated', 'stale', 'old docs', 'doc drift', 'documentation drift',
            'out of date', 'needs update', 'documentation outdated',
        ],
        tables=['confluence_pages'],
        description="Questions about which documentation pages are stale or out of date",
        example_queries=[
            "Which docs are outdated?",
            "Are any documentation pages stale?",
            "What documentation needs to be updated?",
            "Show me the drift status of our docs",
        ]
    ),

    IntentType.GENERAL_QUERY: IntentConfig(
        intent_type=IntentType.GENERAL_QUERY,
        keywords=[],  # Fallback - no specific keywords
        tables=['decisions', 'confluence_pages', 'meetings'],
        description="General questions that don't fit other categories",
        example_queries=[
            "Tell me about the project",
            "What should I know as a new team member?",
        ]
    ),
}


@dataclass
class ClassifiedIntent:
    """Result of intent classification."""
    
    intent_type: IntentType
    confidence: float  # 0.0 to 1.0
    entities: List[str]  # Extracted entities (ticket IDs, names, etc.)
    original_query: str
    
    def to_dict(self) -> dict:
        return {
            'intent_type': self.intent_type.value,
            'confidence': self.confidence,
            'entities': self.entities,
            'original_query': self.original_query
        }


# Entity patterns for extraction
ENTITY_PATTERNS = {
    'ticket_id': r'\b(ONBOARD-\d+)\b',
    'sprint_number': r'\b[Ss]print\s*(\d+)\b',
    'person_first_name': r'\b(Sarah|Marcus|Lisa|Priya|James|Dave)\b',
    'person_full_name': r'\b(Sarah Chen|Marcus Thompson|Lisa Park|Priya Sharma|James O\'Brien|Dave Rossi)\b',
}

# Technical terms to extract as entities
TECH_TERMS = [
    'react', 'django', 'postgresql', 'postgres', 'jwt', 'authentication', 'auth',
    'tailwind', 'material ui', 'mui', 'frontend', 'backend', 'api', 'database',
    'docker', 'ecs', 'fargate', 'aws', 'redis', 'celery', 'testing', 'ci/cd',
    'github', 'git', 'deployment', 'security', 'performance', 'caching'
]
