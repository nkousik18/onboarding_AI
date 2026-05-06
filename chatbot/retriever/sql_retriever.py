"""
SQL Retriever for Phase 1 (v3)

Fixes applied:
1. Better person query handling
2. List all X queries support
3. Role/topic to person mapping
4. Confluence page listing
"""

import sys
import os
import re

RETRIEVER_DIR = os.path.dirname(os.path.abspath(__file__))
CHATBOT_DIR = os.path.dirname(RETRIEVER_DIR)
if CHATBOT_DIR not in sys.path:
    sys.path.insert(0, CHATBOT_DIR)

from django_setup import get_models
from typing import List, Optional
from django.db.models import Q, Count

models = get_models()
Decision = models['Decision']
DecisionConflict = models['DecisionConflict']
Meeting = models['Meeting']
JiraTicket = models['JiraTicket']
ConfluencePage = models['ConfluencePage']
GitCommit = models['GitCommit']
Sprint = models['Sprint']
SprintTicket = models['SprintTicket']
EntityReference = models['EntityReference']

from .base import BaseRetriever, Document
from .people import registry


class SQLRetriever(BaseRetriever):
    """SQL Retriever with improved person and list queries."""
    
    def retrieve(
        self, 
        query: str, 
        intent_type: str, 
        entities: List[str],
        limit: int = 10
    ) -> List[Document]:
        """Route to appropriate retrieval method."""
        
        retrieval_methods = {
            'decision_query': self._retrieve_decisions,
            'person_query': self._retrieve_person_info,
            'timeline_query': self._retrieve_timeline,
            'howto_query': self._retrieve_documentation,
            'status_query': self._retrieve_status,
            'ticket_query': self._retrieve_ticket_info,
            'meeting_query': self._retrieve_meetings,
            'sprint_summary_query': self._retrieve_sprint_summary,
            'conflict_query': self._retrieve_conflicts,
            'provenance_query': self._retrieve_provenance,
            'general_query': self._retrieve_general,
        }
        
        # Check for "list all" type queries
        if self._is_list_query(query):
            return self._retrieve_list(query, entities, limit)
        
        method = retrieval_methods.get(intent_type, self._retrieve_general)
        return method(query, entities, limit)
    
    def _is_list_query(self, query: str) -> bool:
        """Check if query is asking for a list of items."""
        query_lower = query.lower()
        list_patterns = [
            'list all', 'show all', 'what are all', 'all the',
            'available', 'what pages', 'what documents', 'what decisions',
            'what meetings', 'what tickets'
        ]
        return any(pattern in query_lower for pattern in list_patterns)
    
    def _retrieve_list(self, query: str, entities: List[str], limit: int) -> List[Document]:
        """Handle list queries."""
        query_lower = query.lower()
        documents = []
        
        if 'confluence' in query_lower or 'page' in query_lower or 'document' in query_lower:
            # List all Confluence pages
            pages = ConfluencePage.objects.all()[:limit]
            for page in pages:
                documents.append(self._confluence_to_document(page))
            
            # Add summary document
            if documents:
                summary = Document(
                    content=f"Found {len(documents)} Confluence pages:\n" + 
                            "\n".join([f"- {d.title}" for d in documents]),
                    title=f"Confluence Pages Summary ({len(documents)} pages)",
                    source_type='summary',
                    source_id='',
                    source_table='confluence_pages',
                    date=None,
                    related_tickets=[],
                    related_people=[],
                    metadata={'count': len(documents)}
                )
                documents.insert(0, summary)
        
        elif 'decision' in query_lower:
            decisions = Decision.objects.filter(status='active').order_by('-decision_date')[:limit]
            for d in decisions:
                documents.append(self._decision_to_document(d))
            
            if documents:
                summary = Document(
                    content=f"Found {len(documents)} active decisions:\n" + 
                            "\n".join([f"- {d.title}" for d in documents]),
                    title=f"Decisions Summary ({len(documents)} decisions)",
                    source_type='summary',
                    source_id='',
                    source_table='decisions',
                    date=None,
                    related_tickets=[],
                    related_people=[],
                    metadata={'count': len(documents)}
                )
                documents.insert(0, summary)
        
        elif 'meeting' in query_lower:
            meetings = Meeting.objects.all().order_by('-meeting_date')[:limit]
            for m in meetings:
                documents.append(self._meeting_to_document(m))
            
            if documents:
                summary = Document(
                    content=f"Found {len(documents)} meetings:\n" + 
                            "\n".join([f"- {d.title} ({d.date})" for d in documents]),
                    title=f"Meetings Summary ({len(documents)} meetings)",
                    source_type='summary',
                    source_id='',
                    source_table='meetings',
                    date=None,
                    related_tickets=[],
                    related_people=[],
                    metadata={'count': len(documents)}
                )
                documents.insert(0, summary)
        
        elif 'ticket' in query_lower:
            tickets = JiraTicket.objects.all().order_by('-created_date')[:limit]
            for t in tickets:
                documents.append(self._ticket_to_document(t))
        
        return documents
    
    def _normalize_person_name(self, name: str) -> Optional[str]:
        """Normalize person name to full canonical name via registry."""
        return registry.normalize_name(name) or name
    
    def _extract_sprint_number(self, query: str, entities: List[str]) -> Optional[int]:
        """Extract the first sprint number from query or entities."""
        for entity in entities:
            if isinstance(entity, str) and entity.isdigit():
                return int(entity)
            match = re.search(r'(\d+)', str(entity))
            if match:
                return int(match.group(1))

        match = re.search(r'sprint\s*(\d+)', query.lower())
        if match:
            return int(match.group(1))

        return None

    def _extract_all_sprint_numbers(self, query: str, entities: List[str]) -> List[int]:
        """Extract all sprint numbers mentioned in a query (e.g. 'sprint 2 and sprint 3')."""
        nums = []
        for entity in entities:
            if isinstance(entity, str) and entity.isdigit():
                n = int(entity)
                if n not in nums:
                    nums.append(n)
        for m in re.finditer(r'sprint\s*(\d+)', query.lower()):
            n = int(m.group(1))
            if n not in nums:
                nums.append(n)
        return nums
    
    def retrieve_by_id(self, source_type: str, source_id: str) -> Optional[Document]:
        """Retrieve a specific document by ID."""
        try:
            if source_type == 'decision':
                obj = Decision.objects.get(id=source_id)
                return self._decision_to_document(obj)
            elif source_type == 'meeting':
                obj = Meeting.objects.get(id=source_id)
                return self._meeting_to_document(obj)
            elif source_type == 'jira':
                obj = JiraTicket.objects.get(id=source_id)
                return self._ticket_to_document(obj)
            elif source_type == 'confluence':
                obj = ConfluencePage.objects.get(id=source_id)
                return self._confluence_to_document(obj)
        except Exception:
            pass
        return None
    
    # =========================================
    # PERSON QUERIES (IMPROVED)
    # =========================================
    
    def _retrieve_person_info(self, query: str, entities: List[str], limit: int) -> List[Document]:
        """
        Retrieve information about people via PeopleRegistry (no hardcoded names/roles).
        Resolution order:
          1. Normalize entity strings to canonical names via registry
          2. Scan query words for name variants
          3. Fallback: find_by_role_keywords → evidence-based topic attribution
        """
        documents = []

        # 1. Resolve entities to canonical names
        person_names = []
        for entity in entities:
            if isinstance(entity, str):
                canonical = registry.normalize_name(entity)
                if canonical and canonical not in person_names:
                    person_names.append(canonical)

        # 2. Scan individual query words for name variants
        for word in query.lower().split():
            canonical = registry.normalize_name(word)
            if canonical and canonical not in person_names:
                person_names.append(canonical)

        self._log(f"Person names found: {person_names}")

        if person_names:
            for name in person_names:
                work = registry.get_person_work(name)

                for commit in work['commits']:
                    documents.append(self._commit_to_document(commit))
                for ticket in work['tickets']:
                    documents.append(self._ticket_to_document(ticket))
                for decision in work['decisions']:
                    documents.append(self._decision_to_document(decision))

                if documents:
                    summary = self._create_person_summary(name, work['role'], documents)
                    documents.insert(0, summary)

            return documents[:limit]

        # 3. No explicit name — try role keywords, then evidence-based topic attribution
        matched_names = registry.find_by_role_keywords(query)
        if matched_names:
            return self._retrieve_person_info(query, matched_names, limit)

        for word in query.lower().split():
            if len(word) > 4:
                contributors = registry.get_topic_contributors(word)
                if contributors:
                    top_name = contributors[0][0]
                    return self._retrieve_person_info(query, [top_name], limit)

        return []

    def _create_person_summary(self, name: str, role: str, documents: List[Document]) -> Document:
        """Create a summary document for a person."""
        commits = [d for d in documents if d.source_type == 'commit']
        tickets = [d for d in documents if d.source_type == 'jira']
        decisions = [d for d in documents if d.source_type == 'decision']

        content = f"SUMMARY FOR {name.upper()} — {role}\n\n"
        content += f"Commits: {len(commits)}\nTickets: {len(tickets)}\nDecisions involved: {len(decisions)}\n\n"

        if commits:
            content += "Recent Commits:\n"
            for c in commits[:3]:
                content += f"  - {c.title}\n"
            content += "\n"

        if tickets:
            content += "Assigned Tickets:\n"
            for t in tickets[:3]:
                content += f"  - {t.title}\n"
            content += "\n"

        if decisions:
            content += "Decisions Involved:\n"
            for d in decisions[:3]:
                content += f"  - {d.title}\n"

        return Document(
            content=content,
            title=f"{name} - Work Summary",
            source_type='person_summary',
            source_id='',
            source_table='',
            date=None,
            related_tickets=[t.related_tickets[0] for t in tickets if t.related_tickets],
            related_people=[name],
            relevance_score=1.0,
            metadata={
                'person_name': name,
                'role': role,
                'commit_count': len(commits),
                'ticket_count': len(tickets),
                'decision_count': len(decisions),
            }
        )
    
    def _log(self, message: str):
        """Debug logging."""
        # Uncomment for debugging:
        # print(f"[Retriever] {message}")
        pass
    
    # =========================================
    # SPRINT SUMMARY QUERY
    # =========================================
    
    def _retrieve_sprint_summary(self, query: str, entities: List[str], limit: int) -> List[Document]:
        """Retrieve sprint summary. Handles multiple sprint numbers in one query."""
        sprint_nums = self._extract_all_sprint_numbers(query, entities)

        if not sprint_nums:
            return self._retrieve_all_sprints_overview(limit)

        documents = []
        for sprint_num in sprint_nums:
            try:
                sprint = Sprint.objects.get(sprint_number=sprint_num)
                sprint_data = self._aggregate_sprint_data(sprint)
                documents.append(self._sprint_data_to_document(sprint, sprint_data))
            except Sprint.DoesNotExist:
                latest = Sprint.objects.order_by('-sprint_number').first()
                latest_msg = f" The latest sprint is Sprint {latest.sprint_number}." if latest else ""
                documents.append(Document(
                    content=f"Sprint {sprint_num} hasn't been planned yet.{latest_msg}",
                    title=f"Sprint {sprint_num} — Not Yet Planned",
                    source_type='error',
                    source_id='',
                    source_table='sprints',
                    date=None,
                    related_tickets=[],
                    related_people=[],
                    metadata={'error': True}
                ))

        return documents
    
    def _aggregate_sprint_data(self, sprint: Sprint) -> dict:
        """Aggregate all data for a sprint."""
        start_date = sprint.start_date
        end_date = sprint.end_date
        
        sprint_ticket_ids = SprintTicket.objects.filter(
            sprint=sprint
        ).values_list('ticket_id', flat=True)
        
        tickets = JiraTicket.objects.filter(id__in=sprint_ticket_ids)
        
        tickets_by_status = {}
        for ticket in tickets:
            status = ticket.status or 'Unknown'
            if status not in tickets_by_status:
                tickets_by_status[status] = []
            tickets_by_status[status].append(ticket)
        
        decisions = Decision.objects.filter(
            decision_date__gte=start_date,
            decision_date__lte=end_date
        ).order_by('decision_date')
        
        meetings = Meeting.objects.filter(
            meeting_date__gte=start_date,
            meeting_date__lte=end_date
        ).order_by('meeting_date')
        
        commits = GitCommit.objects.filter(
            commit_date__date__gte=start_date,
            commit_date__date__lte=end_date
        ).order_by('commit_date')
        
        contributors = set()
        for ticket in tickets:
            if ticket.assignee:
                contributors.add(ticket.assignee)
            if ticket.reporter:
                contributors.add(ticket.reporter)
        for commit in commits:
            if commit.author_name:
                contributors.add(commit.author_name)
        
        return {
            'tickets': list(tickets),
            'tickets_by_status': tickets_by_status,
            'decisions': list(decisions),
            'meetings': list(meetings),
            'commits': list(commits),
            'contributors': list(contributors),
            'stats': {
                'total_tickets': tickets.count(),
                'completed_tickets': tickets.filter(status__icontains='done').count(),
                'in_progress_tickets': tickets.filter(
                    Q(status__icontains='progress') | Q(status__icontains='review')
                ).count(),
                'open_tickets': tickets.filter(
                    Q(status__icontains='open') | Q(status__icontains='todo')
                ).count(),
                'total_decisions': decisions.count(),
                'total_meetings': meetings.count(),
                'total_commits': commits.count(),
                'total_contributors': len(contributors),
            }
        }
    
    def _sprint_data_to_document(self, sprint: Sprint, data: dict) -> Document:
        """Convert sprint data to Document."""
        content_parts = []
        stats = data['stats']
        
        content_parts.append(f"SPRINT {sprint.sprint_number}: {sprint.name}")
        content_parts.append(f"Duration: {sprint.start_date} to {sprint.end_date}")
        if sprint.goal:
            content_parts.append(f"Goal: {sprint.goal}")
        content_parts.append("")
        
        content_parts.append("STATISTICS:")
        content_parts.append(f"- Total Tickets: {stats['total_tickets']}")
        content_parts.append(f"- Completed: {stats['completed_tickets']}")
        content_parts.append(f"- In Progress: {stats['in_progress_tickets']}")
        content_parts.append(f"- Open/To Do: {stats['open_tickets']}")
        content_parts.append(f"- Decisions Made: {stats['total_decisions']}")
        content_parts.append(f"- Meetings Held: {stats['total_meetings']}")
        content_parts.append(f"- Commits: {stats['total_commits']}")
        content_parts.append(f"- Contributors: {stats['total_contributors']}")
        content_parts.append("")
        
        content_parts.append("TICKETS BY STATUS:")
        for status, tickets in data['tickets_by_status'].items():
            content_parts.append(f"  {status}:")
            for ticket in tickets[:5]:
                assignee = f" ({ticket.assignee})" if ticket.assignee else ""
                content_parts.append(f"    - {ticket.issue_key}: {ticket.summary}{assignee}")
            if len(tickets) > 5:
                content_parts.append(f"    ... and {len(tickets) - 5} more")
        content_parts.append("")
        
        if data['decisions']:
            content_parts.append("KEY DECISIONS:")
            for decision in data['decisions'][:5]:
                content_parts.append(f"  - {decision.title}")
            content_parts.append("")
        
        if data['meetings']:
            content_parts.append("MEETINGS:")
            for meeting in data['meetings']:
                content_parts.append(f"  - {meeting.title} ({meeting.meeting_date})")
            content_parts.append("")
        
        if data['contributors']:
            content_parts.append("CONTRIBUTORS:")
            for contributor in list(data['contributors'])[:10]:
                content_parts.append(f"  - {contributor}")
        
        related_tickets = [t.issue_key for t in data['tickets']]
        
        return Document(
            content="\n".join(content_parts),
            title=f"Sprint {sprint.sprint_number} Summary: {sprint.name}",
            source_type='sprint_summary',
            source_id=str(sprint.id),
            source_table='sprints',
            date=sprint.start_date,
            related_tickets=related_tickets,
            related_people=list(data['contributors']),
            relevance_score=1.0,
            metadata={'sprint_number': sprint.sprint_number, 'stats': stats}
        )
    
    def _retrieve_all_sprints_overview(self, limit: int) -> List[Document]:
        """Retrieve all sprints overview."""
        documents = []
        sprints = Sprint.objects.all().order_by('sprint_number')[:limit]
        for sprint in sprints:
            data = self._aggregate_sprint_data(sprint)
            documents.append(self._sprint_data_to_document(sprint, data))
        return documents
    
    # =========================================
    # STATUS QUERIES
    # =========================================
    
    def _retrieve_status(self, query: str, entities: List[str], limit: int) -> List[Document]:
        """Retrieve status information."""
        documents = []
        
        ticket_ids = [e for e in entities if isinstance(e, str) and 'ONBOARD-' in e.upper()]
        
        if ticket_ids:
            for ticket_id in ticket_ids:
                ticket = JiraTicket.objects.filter(issue_key__iexact=ticket_id).first()
                if ticket:
                    documents.append(self._ticket_to_document(ticket))
            return documents
        
        sprint_num = self._extract_sprint_number(query, entities)
        
        if sprint_num:
            try:
                sprint = Sprint.objects.get(sprint_number=sprint_num)
                sprint_ticket_ids = SprintTicket.objects.filter(
                    sprint=sprint
                ).values_list('ticket_id', flat=True)
                
                tickets = JiraTicket.objects.filter(id__in=sprint_ticket_ids)
                
                if not tickets.exists():
                    return [Document(
                        content=f"No tickets found for Sprint {sprint_num}.",
                        title=f"Sprint {sprint_num} - No Tickets",
                        source_type='error',
                        source_id='',
                        source_table='sprints',
                        date=None,
                        related_tickets=[],
                        related_people=[],
                        metadata={'error': True}
                    )]
                
                summary = self._create_sprint_status_summary(sprint, tickets)
                documents.append(summary)
                
                for ticket in tickets[:limit-1]:
                    documents.append(self._ticket_to_document(ticket))
                
                return documents
                
            except Sprint.DoesNotExist:
                return [Document(
                    content=f"Sprint {sprint_num} not found.",
                    title=f"Sprint {sprint_num} Not Found",
                    source_type='error',
                    source_id='',
                    source_table='sprints',
                    date=None,
                    related_tickets=[],
                    related_people=[],
                    metadata={'error': True}
                )]
        
        # Default: get non-done tickets
        tickets = JiraTicket.objects.exclude(
            status__icontains='done'
        ).order_by('-updated_date')[:limit]
        
        if not tickets.exists():
            tickets = JiraTicket.objects.all().order_by('-updated_date')[:limit]
        
        for ticket in tickets:
            documents.append(self._ticket_to_document(ticket))
        
        return documents
    
    def _create_sprint_status_summary(self, sprint: Sprint, tickets) -> Document:
        """Create sprint status summary."""
        total = tickets.count()
        done = tickets.filter(status__icontains='done').count()
        in_progress = tickets.filter(
            Q(status__icontains='progress') | Q(status__icontains='review')
        ).count()
        open_count = tickets.filter(
            Q(status__icontains='open') | Q(status__icontains='todo')
        ).count()
        blocked = tickets.filter(status__icontains='block').count()
        
        completion_pct = (done / total * 100) if total > 0 else 0
        
        if completion_pct == 100:
            status_label = "✅ COMPLETED"
        elif completion_pct >= 75:
            status_label = "🟢 ON TRACK"
        elif completion_pct >= 50:
            status_label = "🟡 IN PROGRESS"
        else:
            status_label = "🔴 NEEDS ATTENTION"
        
        content = f"""SPRINT {sprint.sprint_number} STATUS: {status_label}

Sprint: {sprint.name}
Duration: {sprint.start_date} to {sprint.end_date}

TICKET BREAKDOWN:
- Total: {total}
- ✅ Done: {done}
- 🔄 In Progress: {in_progress}
- 📋 Open/To Do: {open_count}
- 🚫 Blocked: {blocked}

PROGRESS: {done}/{total} ({completion_pct:.0f}%)
"""
        
        if completion_pct == 100:
            content += f"\n🎉 All Sprint {sprint.sprint_number} tickets completed!"
        
        return Document(
            content=content,
            title=f"Sprint {sprint.sprint_number} Status: {status_label}",
            source_type='sprint_status',
            source_id=str(sprint.id),
            source_table='sprints',
            date=sprint.start_date,
            related_tickets=[],
            related_people=[],
            relevance_score=1.0,
            metadata={'sprint_number': sprint.sprint_number, 'completion': completion_pct}
        )
    
    # =========================================
    # DECISION QUERIES
    # =========================================
    
    def _retrieve_decisions(self, query: str, entities: List[str], limit: int) -> List[Document]:
        """Retrieve decisions.

        When no specific entity is mentioned (e.g. 'what are the key decisions?'),
        order by decision_date ascending so foundational Sprint-1 decisions surface
        first rather than the most recently extracted records.
        """
        documents = []
        q_filter = Q()

        for entity in entities:
            if isinstance(entity, str):
                q_filter |= Q(title__icontains=entity)
                q_filter |= Q(description__icontains=entity)
                q_filter |= Q(rationale__icontains=entity)
                q_filter |= Q(alternatives_considered__icontains=entity)

        has_specific_filter = bool(entities)

        _DECISION_STOPWORDS = {
            'what', 'are', 'were', 'key', 'the', 'all', 'list', 'show', 'give',
            'tell', 'taken', 'made', 'main', 'decision', 'decisions', 'about',
            'have', 'been', 'that', 'this', 'some', 'any', 'our', 'your',
        }
        if not entities:
            topic_words = [
                w for w in query.lower().split()
                if len(w) > 3 and w not in _DECISION_STOPWORDS
            ]
            for word in topic_words:
                q_filter |= Q(title__icontains=word)
                q_filter |= Q(rationale__icontains=word)

        # Unfiltered "list all" query — ascending date surfaces original decisions first
        order = 'decision_date' if not has_specific_filter else '-decision_date'
        decisions = Decision.objects.filter(status='active').filter(q_filter).order_by(order)

        # Deduplicate by normalised title to avoid showing 3 copies of "Use JWT"
        seen_titles: set = set()
        for decision in decisions:
            normalised = re.sub(r'\s+', ' ', decision.title.lower().strip())
            # Strip common action prefixes before deduplication
            for prefix in ('use ', 'using ', 'adopt ', 'switch to ', 'switch from '):
                if normalised.startswith(prefix):
                    normalised = normalised[len(prefix):]
                    break
            if normalised not in seen_titles:
                seen_titles.add(normalised)
                documents.append(self._decision_to_document(decision))
            if len(documents) >= limit:
                break

        return documents
    
    def _decision_to_document(self, decision: Decision) -> Document:
        """Convert Decision to Document."""
        content_parts = []
        
        if decision.description:
            content_parts.append(f"Description: {decision.description}")
        if decision.rationale:
            content_parts.append(f"Rationale: {decision.rationale}")
        if decision.alternatives_considered:
            content_parts.append(f"Alternatives: {decision.alternatives_considered}")
        if decision.impact:
            content_parts.append(f"Impact: {decision.impact}")
        
        return Document(
            content="\n".join(content_parts),
            title=decision.title,
            source_type='decision',
            source_id=str(decision.id),
            source_table='decisions',
            date=decision.decision_date,
            related_tickets=decision.related_tickets or [],
            related_people=decision.decided_by or [],
            metadata={
                'category': decision.category,
                'status': decision.status,
            }
        )
    
    # =========================================
    # DOCUMENTATION QUERIES
    # =========================================
    
    def _retrieve_documentation(self, query: str, entities: List[str], limit: int) -> List[Document]:
        """Retrieve Confluence documentation."""
        documents = []
        
        q_filter = Q()
        
        for entity in entities:
            if isinstance(entity, str):
                q_filter |= Q(title__icontains=entity)
                q_filter |= Q(content__icontains=entity)
        
        keywords = ['setup', 'install', 'configure', 'guide', 'start', 'api', 'architecture']
        for keyword in keywords:
            if keyword in query.lower():
                q_filter |= Q(title__icontains=keyword)
                q_filter |= Q(content__icontains=keyword)
        
        pages = ConfluencePage.objects.filter(q_filter)[:limit]
        
        for page in pages:
            documents.append(self._confluence_to_document(page))
        
        if not documents:
            pages = ConfluencePage.objects.all()[:limit]
            for page in pages:
                documents.append(self._confluence_to_document(page))
        
        return documents
    
    def _confluence_to_document(self, page: ConfluencePage) -> Document:
        """Convert ConfluencePage to Document."""
        return Document(
            content=page.content or "",
            title=page.title,
            source_type='confluence',
            source_id=str(page.id),
            source_table='confluence_pages',
            date=page.page_created_date.date() if page.page_created_date else None,
            related_people=[page.author] if page.author else [],
            metadata={
                'author': page.author,
                'labels': page.labels,
            }
        )
    
    # =========================================
    # TICKET QUERIES
    # =========================================
    
    def _retrieve_ticket_info(self, query: str, entities: List[str], limit: int) -> List[Document]:
        """Retrieve ticket information."""
        documents = []
        
        ticket_ids = [e for e in entities if isinstance(e, str) and 'ONBOARD-' in e.upper()]
        
        for ticket_id in ticket_ids:
            ticket = JiraTicket.objects.filter(issue_key__iexact=ticket_id).first()
            
            if ticket:
                documents.append(self._ticket_to_document(ticket))
                
                commits = GitCommit.objects.filter(message__icontains=ticket_id)[:3]
                for commit in commits:
                    documents.append(self._commit_to_document(commit))
                
                decisions = Decision.objects.filter(related_tickets__contains=[ticket_id])[:2]
                for decision in decisions:
                    documents.append(self._decision_to_document(decision))
        
        return documents[:limit]
    
    def _ticket_to_document(self, ticket: JiraTicket) -> Document:
        """Convert JiraTicket to Document."""
        content_parts = [
            f"Status: {ticket.status}",
            f"Assignee: {ticket.assignee or 'Unassigned'}",
        ]
        
        if ticket.description:
            content_parts.append(f"Description: {ticket.description}")
        if ticket.comments:
            content_parts.append(f"Comments: {ticket.comments[:500]}")
        
        return Document(
            content="\n".join(content_parts),
            title=f"{ticket.issue_key}: {ticket.summary}",
            source_type='jira',
            source_id=str(ticket.id),
            source_table='jira_tickets',
            date=ticket.created_date.date() if ticket.created_date else None,
            related_tickets=[ticket.issue_key],
            related_people=[p for p in [ticket.assignee, ticket.reporter] if p],
            metadata={'status': ticket.status, 'priority': ticket.priority}
        )
    
    def _commit_to_document(self, commit: GitCommit) -> Document:
        """Convert GitCommit to Document."""
        return Document(
            content=commit.message or "",
            title=f"Commit: {(commit.message or '')[:60]}",
            source_type='commit',
            source_id=str(commit.id),
            source_table='git_commits',
            date=commit.commit_date.date() if commit.commit_date else None,
            related_people=[commit.author_name] if commit.author_name else [],
            related_tickets=[commit.related_tickets] if commit.related_tickets else [],
            metadata={'sha': commit.sha}
        )
    
    # =========================================
    # MEETING & TIMELINE QUERIES
    # =========================================
    
    def _retrieve_meetings(self, query: str, entities: List[str], limit: int) -> List[Document]:
        """Retrieve meetings."""
        documents = []
        
        q_filter = Q()
        
        for entity in entities:
            if isinstance(entity, str):
                q_filter |= Q(title__icontains=entity)
                q_filter |= Q(summary__icontains=entity)
        
        for mtype in ['planning', 'standup', 'retrospective', 'review', 'midsprint']:
            if mtype in query.lower():
                q_filter |= Q(title__icontains=mtype)
        
        sprint_num = self._extract_sprint_number(query, entities)
        if sprint_num:
            q_filter |= Q(title__icontains=f'sprint{sprint_num}')
            q_filter |= Q(title__icontains=f'Sprint{sprint_num}')
        
        meetings = Meeting.objects.filter(q_filter).order_by('-meeting_date')[:limit]
        
        for meeting in meetings:
            documents.append(self._meeting_to_document(meeting))
        
        if not documents:
            meetings = Meeting.objects.order_by('-meeting_date')[:limit]
            for meeting in meetings:
                documents.append(self._meeting_to_document(meeting))
        
        return documents
    
    def _meeting_to_document(self, meeting: Meeting) -> Document:
        """Convert Meeting to Document."""
        content_parts = []
        
        if meeting.summary:
            content_parts.append(f"Summary: {meeting.summary}")
        if meeting.key_decisions:
            content_parts.append(f"Key Decisions: {meeting.key_decisions}")
        if meeting.action_items:
            content_parts.append(f"Action Items: {meeting.action_items}")
        
        return Document(
            content="\n".join(content_parts),
            title=meeting.title or "Meeting",
            source_type='meeting',
            source_id=str(meeting.id),
            source_table='meetings',
            date=meeting.meeting_date.date() if meeting.meeting_date else None,
            related_people=[],
            metadata={}
        )
    
    def _retrieve_timeline(self, query: str, entities: List[str], limit: int) -> List[Document]:
        """Retrieve timeline."""
        documents = []
        
        sprint_num = self._extract_sprint_number(query, entities)
        
        if sprint_num:
            try:
                sprint = Sprint.objects.get(sprint_number=sprint_num)
                decisions = Decision.objects.filter(
                    decision_date__gte=sprint.start_date,
                    decision_date__lte=sprint.end_date
                ).order_by('decision_date')
                
                for decision in decisions:
                    documents.append(self._decision_to_document(decision))
            except Sprint.DoesNotExist:
                pass
        
        if not documents:
            decisions = Decision.objects.filter(status='active').order_by('decision_date')[:limit]
            for decision in decisions:
                documents.append(self._decision_to_document(decision))
        
        return documents[:limit]
    
    # =========================================
    # CONFLICT QUERIES
    # =========================================

    def _retrieve_conflicts(self, query: str, entities: List[str], limit: int) -> List[Document]:  # noqa: ARG002
        """Retrieve all detected conflicts, optionally filtered to a specific decision."""
        conflicts = DecisionConflict.objects.select_related(
            'decision_a', 'decision_b'
        ).order_by('-severity', 'decision_a__title')

        # Narrow to a specific decision if an entity matches a title
        if entities:
            for entity in entities:
                if isinstance(entity, str) and len(entity) > 3:
                    filtered = conflicts.filter(
                        Q(decision_a__title__icontains=entity) |
                        Q(decision_b__title__icontains=entity)
                    )
                    if filtered.exists():
                        conflicts = filtered
                        break

        if not conflicts.exists():
            return [Document(
                content="No conflicts have been detected between active decisions.",
                title="No Conflicts Found",
                source_type='conflict_summary',
                source_id='',
                source_table='decision_conflicts',
                date=None,
                related_tickets=[],
                related_people=[],
                metadata={'count': 0}
            )]

        by_sev = {'high': [], 'medium': [], 'low': []}
        for c in conflicts:
            by_sev[c.severity].append(c)

        lines = [f"DETECTED CONFLICTS ({conflicts.count()} total)\n"]
        for sev in ('high', 'medium', 'low'):
            group = by_sev[sev]
            if not group:
                continue
            lines.append(f"── {sev.upper()} SEVERITY ──")
            for c in group:
                lines.append(f"  [{c.conflict_type}]  {c.decision_a.title}")
                lines.append(f"          ↔  {c.decision_b.title}")
                if c.explanation:
                    lines.append(f"          Explanation: {c.explanation}")
                lines.append("")

        lines.append(f"Summary: {len(by_sev['high'])} high, "
                     f"{len(by_sev['medium'])} medium, "
                     f"{len(by_sev['low'])} low severity conflicts.")

        return [Document(
            content="\n".join(lines),
            title=f"Decision Conflicts ({conflicts.count()} detected)",
            source_type='conflict_summary',
            source_id='',
            source_table='decision_conflicts',
            date=None,
            related_tickets=[],
            related_people=[],
            relevance_score=1.0,
            metadata={'count': conflicts.count(), 'severities': {k: len(v) for k, v in by_sev.items()}}
        )]

    # =========================================
    # PROVENANCE QUERIES
    # =========================================

    def _retrieve_provenance(self, query: str, entities: List[str], limit: int) -> List[Document]:
        """Trace origin → tickets → commits for a decision."""
        # Find decision by title keywords from query + entities
        decision = None
        search_terms = list(entities) + [w for w in query.split() if len(w) > 4]

        for term in search_terms:
            if isinstance(term, str) and len(term) >= 3:
                results = Decision.objects.filter(title__icontains=term, status='active')
                if results.count() == 1:
                    decision = results.first()
                    break
                if results.count() > 1:
                    # Prefer exact-ish match
                    decision = results.order_by('decision_date').first()
                    break

        if not decision:
            return [Document(
                content="I couldn't identify which decision you're asking about. "
                        "Try being more specific, e.g. 'trace the JWT decision' or "
                        "'where did the Tailwind decision come from?'",
                title="Decision Not Found",
                source_type='provenance',
                source_id='',
                source_table='decisions',
                date=None,
                related_tickets=[],
                related_people=[],
                metadata={'error': True}
            )]

        # ── Origin ──
        origin_lines = []
        if decision.source_id:
            if decision.source_type == 'meeting':
                m = Meeting.objects.filter(id=decision.source_id).first()
                if m:
                    origin_lines.append(f"Origin: Meeting — {m.title}")
                    if m.meeting_date:
                        origin_lines.append(f"Date: {m.meeting_date.strftime('%Y-%m-%d')}")
                    if m.participants:
                        import re as _re
                        parts = list(set(_re.findall(r'[A-Z][a-z]+ [A-Z][a-z]+', m.participants)))[:6]
                        if parts:
                            origin_lines.append(f"Participants: {', '.join(parts)}")
            elif decision.source_type == 'confluence':
                cp = ConfluencePage.objects.filter(id=decision.source_id).first()
                if cp:
                    origin_lines.append(f"Origin: Confluence — {cp.title}")
                    if cp.author:
                        origin_lines.append(f"Author: {cp.author}")
            elif decision.source_type == 'jira':
                jt = JiraTicket.objects.filter(id=decision.source_id).first()
                if jt:
                    origin_lines.append(f"Origin: Jira — {jt.issue_key}: {jt.summary}")

        # ── Tickets ──
        ticket_keys = []
        if decision.source_id:
            refs = EntityReference.objects.filter(
                source_type=decision.source_type,
                source_id=decision.source_id,
                reference_type='jira_ticket',
            )
            ticket_keys = [r.reference_id for r in refs
                           if r.reference_id and not r.reference_id[:4].isdigit()]
        if decision.related_tickets:
            ticket_keys = list(set(ticket_keys + list(decision.related_tickets)))

        ticket_lines = []
        ticket_objs = []
        for key in ticket_keys[:8]:
            jt = JiraTicket.objects.filter(issue_key=key).first()
            if jt:
                assignee = f" → {jt.assignee}" if jt.assignee else ""
                ticket_lines.append(f"  {jt.issue_key} [{jt.status}]  {jt.summary[:60]}{assignee}")
                ticket_objs.append(jt)
            else:
                ticket_lines.append(f"  {key}")

        # ── Commits ──
        commit_lines = []
        seen_ids = set()

        for key in ticket_keys:
            for ref in EntityReference.objects.filter(
                source_type='commit', reference_type='jira_ticket', reference_id=key
            ):
                if ref.source_id in seen_ids:
                    continue
                gc = GitCommit.objects.filter(id=ref.source_id).first()
                if gc:
                    seen_ids.add(ref.source_id)
                    date = gc.commit_date.strftime('%Y-%m-%d') if gc.commit_date else '?'
                    sha = gc.sha[:8] if gc.sha else str(gc.id)[:8]
                    commit_lines.append(
                        f"  [{date}] {sha}  {gc.message.split(chr(10))[0][:70]}  ({gc.author_name})"
                    )

        for tag in (decision.tags or []):
            for gc in GitCommit.objects.filter(message__icontains=tag).order_by('commit_date')[:5]:
                if gc.id in seen_ids:
                    continue
                seen_ids.add(gc.id)
                date = gc.commit_date.strftime('%Y-%m-%d') if gc.commit_date else '?'
                sha = gc.sha[:8] if gc.sha else str(gc.id)[:8]
                commit_lines.append(
                    f"  [{date}] {sha}  {gc.message.split(chr(10))[0][:70]}  ({gc.author_name})"
                )

        commit_lines = sorted(set(commit_lines))[:12]

        # ── Conflicts ──
        conflict_lines = []
        for c in DecisionConflict.objects.filter(
            Q(decision_a=decision) | Q(decision_b=decision)
        ).select_related('decision_a', 'decision_b'):
            other = c.decision_b if c.decision_a_id == decision.id else c.decision_a
            conflict_lines.append(
                f"  [{c.severity.upper()}] {c.conflict_type} ↔ {other.title[:60]}"
            )
            if c.explanation:
                conflict_lines.append(f"        {c.explanation[:100]}")

        # ── Assemble document ──
        parts = [
            f"PROVENANCE CHAIN: {decision.title}",
            f"Date: {decision.decision_date}  |  Category: {decision.category or 'unknown'}  |  Status: {decision.status}",
            "",
        ]
        if decision.rationale:
            parts += ["WHY:", f"  {decision.rationale[:300]}", ""]
        if decision.tags:
            parts.append(f"Tags: {', '.join(decision.tags)}\n")

        parts.append(f"ORIGIN:")
        parts += (origin_lines if origin_lines else ["  (not recorded)"])
        parts.append("")

        parts.append(f"LINKED TICKETS ({len(ticket_keys)}):")
        parts += (ticket_lines if ticket_lines else ["  none"])
        parts.append("")

        parts.append(f"COMMITS ({len(commit_lines)}):")
        parts += (commit_lines if commit_lines else ["  none found"])
        parts.append("")

        if conflict_lines:
            parts.append("KNOWN CONFLICTS:")
            parts += conflict_lines
            parts.append("")

        if decision.superseded_by:
            parts.append(f"SUPERSEDED BY: {decision.superseded_by.title}")

        related_tickets = [t.issue_key for t in ticket_objs]
        related_people = list(set(
            (decision.decided_by or []) +
            [t.assignee for t in ticket_objs if t.assignee]
        ))

        return [Document(
            content="\n".join(parts),
            title=f"Provenance: {decision.title[:60]}",
            source_type='provenance',
            source_id=str(decision.id),
            source_table='decisions',
            date=decision.decision_date,
            related_tickets=related_tickets,
            related_people=related_people,
            relevance_score=1.0,
            metadata={
                'decision_title': decision.title,
                'ticket_count': len(ticket_keys),
                'commit_count': len(commit_lines),
                'has_conflicts': bool(conflict_lines),
            }
        )]

    def _retrieve_general(self, query: str, entities: List[str], limit: int) -> List[Document]:
        """General fallback."""
        documents = []
        
        decisions = Decision.objects.filter(status='active').order_by('-decision_date')[:3]
        for d in decisions:
            documents.append(self._decision_to_document(d))
        
        overview = ConfluencePage.objects.filter(
            Q(title__icontains='overview') | Q(title__icontains='project')
        ).first()
        if overview:
            documents.append(self._confluence_to_document(overview))
        
        return documents[:limit]


if __name__ == "__main__":
    print("Testing SQL Retriever v3...")
    retriever = SQLRetriever()
    
    tests = [
        ("person_query", ["Marcus"], "What has Marcus been working on?"),
        ("person_query", ["Lisa Park"], "Who worked on the frontend?"),
        ("general_query", [], "What Confluence pages are available?"),
    ]
    
    for intent, entities, query in tests:
        print(f"\n{'='*50}")
        print(f"Query: {query}")
        docs = retriever.retrieve(query, intent, entities, limit=5)
        print(f"Found {len(docs)} documents:")
        for d in docs:
            print(f"  - {d.source_type}: {d.title[:50]}")
