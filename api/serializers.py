import json
from rest_framework import serializers
from knowledge_base.models import (
    GitCommit, GitCommitFile, JiraTicket, ConfluencePage,
    Meeting, Project, ProjectEntity, EntityReference,
    Employee, Sprint, SprintTicket, Decision,
)


def parse_vtt_transcript(vtt_content):
    """Strip VTT headers and timestamps, return clean speaker dialogue."""
    if not vtt_content:
        return ''
    lines = []
    for line in vtt_content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line == 'WEBVTT':
            continue
        if '-->' in line:
            continue
        if line.startswith('NOTE'):
            continue
        lines.append(line)
    return '\n\n'.join(lines)


def parse_json_list(value):
    """Parse a JSON string into a list, or return empty list on failure."""
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


class GitCommitFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = GitCommitFile
        fields = ['id', 'filename', 'additions', 'deletions', 'status']


class GitCommitSerializer(serializers.ModelSerializer):
    files = GitCommitFileSerializer(many=True, read_only=True)
    related_tickets = serializers.SerializerMethodField()

    class Meta:
        model = GitCommit
        fields = [
            'id', 'sha', 'author_name', 'author_email',
            'commit_date', 'message', 'related_tickets', 'files',
        ]

    def get_related_tickets(self, obj):
        if not obj.related_tickets:
            return []
        return [t.strip() for t in obj.related_tickets.split(',') if t.strip()]


class JiraTicketSerializer(serializers.ModelSerializer):
    is_completed = serializers.SerializerMethodField()
    teammates = serializers.SerializerMethodField()
    teammates_count = serializers.SerializerMethodField()

    class Meta:
        model = JiraTicket
        fields = [
            'id', 'issue_key', 'issue_type', 'summary', 'description',
            'status', 'is_completed', 'priority',
            'assignee', 'reporter', 'teammates', 'teammates_count',
            'created_date', 'updated_date', 'resolved_date',
            'labels', 'epic_link', 'sprint', 'story_points', 'comments',
        ]

    def get_is_completed(self, obj):
        return obj.status.lower() in {'done', 'closed', 'resolved', 'complete', 'completed'}

    def get_teammates(self, obj):
        people = set()
        if obj.assignee:
            people.add(obj.assignee.strip())
        if obj.reporter:
            people.add(obj.reporter.strip())
        return sorted(people)

    def get_teammates_count(self, obj):
        return len(self.get_teammates(obj))

    def get_labels(self, obj):
        if not obj.labels:
            return []
        return [l.strip() for l in obj.labels.split(';') if l.strip()]

    labels = serializers.SerializerMethodField()


class ConfluencePageListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfluencePage
        fields = [
            'id', 'title', 'space', 'author', 'labels',
            'version', 'page_created_date', 'page_updated_date',
        ]


class ConfluencePageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfluencePage
        fields = [
            'id', 'title', 'space', 'author', 'content', 'labels',
            'version', 'page_created_date', 'page_updated_date', 'source_filename',
        ]


class MeetingListSerializer(serializers.ModelSerializer):
    meeting_date = serializers.DateTimeField(format='%Y-%m-%d')
    participants = serializers.SerializerMethodField()
    key_decisions = serializers.SerializerMethodField()
    action_items = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = [
            'id', 'title', 'meeting_date', 'summary',
            'key_decisions', 'action_items', 'participants',
            'duration_seconds', 'source_filename',
        ]

    def get_participants(self, obj):
        return parse_json_list(obj.participants)

    def get_key_decisions(self, obj):
        return parse_json_list(obj.key_decisions)

    def get_action_items(self, obj):
        return parse_json_list(obj.action_items)


class MeetingDetailSerializer(serializers.ModelSerializer):
    meeting_date = serializers.DateTimeField(format='%Y-%m-%d')
    participants = serializers.SerializerMethodField()
    key_decisions = serializers.SerializerMethodField()
    action_items = serializers.SerializerMethodField()
    transcript = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = [
            'id', 'title', 'meeting_date', 'transcript', 'summary',
            'key_decisions', 'action_items', 'participants',
            'duration_seconds', 'source_filename',
        ]

    def get_participants(self, obj):
        return parse_json_list(obj.participants)

    def get_key_decisions(self, obj):
        return parse_json_list(obj.key_decisions)

    def get_action_items(self, obj):
        return parse_json_list(obj.action_items)

    def get_transcript(self, obj):
        return parse_vtt_transcript(obj.raw_vtt_content)


class ProjectEntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectEntity
        fields = ['id', 'entity_type', 'entity_id', 'added_manually']


class ProjectSerializer(serializers.ModelSerializer):
    entities = ProjectEntitySerializer(many=True, read_only=True)
    team_members = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'status',
            'epic_key', 'jira_project_key', 'github_repo', 'confluence_space_key',
            'start_date', 'target_end_date', 'actual_end_date',
            'owner', 'team_members', 'tags', 'entities',
        ]

    def get_team_members(self, obj):
        return parse_json_list(obj.team_members)


class EntityReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntityReference
        fields = ['id', 'source_type', 'source_id', 'reference_type', 'reference_id', 'extraction_method']


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = [
            'id', 'name', 'email', 'role', 'department',
            'source', 'jira_account_id', 'github_username', 'is_active',
            'created_at',
        ]


class SprintTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = SprintTicket
        fields = ['id', 'sprint', 'ticket', 'added_date']


class SprintSerializer(serializers.ModelSerializer):
    sprint_tickets = SprintTicketSerializer(many=True, read_only=True)

    class Meta:
        model = Sprint
        fields = [
            'id', 'sprint_number', 'name', 'start_date', 'end_date',
            'goal', 'project', 'status', 'sprint_tickets',
        ]


class DecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Decision
        fields = [
            'id', 'title', 'description', 'decision_date',
            'rationale', 'alternatives_considered', 'impact',
            'decided_by', 'source_type', 'source_id', 'source_title',
            'related_tickets', 'related_decisions',
            'category', 'tags', 'status',
            'superseded_by', 'supersedes', 'confidence_score', 'extraction_notes',
        ]


class SprintOutcomeSerializer(serializers.ModelSerializer):
    tickets = serializers.SerializerMethodField()
    total_tickets = serializers.SerializerMethodField()
    completed_count = serializers.SerializerMethodField()
    pending_count = serializers.SerializerMethodField()

    class Meta:
        model = Sprint
        fields = [
            'id', 'sprint_number', 'name', 'start_date', 'end_date',
            'goal', 'status', 'total_tickets', 'completed_count', 'pending_count',
            'tickets',
        ]

    def _get_tickets(self, obj):
        return [st.ticket for st in obj.sprint_tickets.select_related('ticket').all()]

    def get_tickets(self, obj):
        return JiraTicketSerializer(self._get_tickets(obj), many=True).data

    def get_total_tickets(self, obj):
        return obj.sprint_tickets.count()

    def get_completed_count(self, obj):
        completed_statuses = {'done', 'closed', 'resolved', 'complete', 'completed'}
        return sum(
            1 for st in obj.sprint_tickets.select_related('ticket').all()
            if st.ticket.status.lower() in completed_statuses
        )

    def get_pending_count(self, obj):
        return self.get_total_tickets(obj) - self.get_completed_count(obj)


# ── Chrome Extension Serializers ───────────────────────────────────────────────

class TicketCommentSerializer(serializers.Serializer):
    """Serializer for ticket comments."""
    id = serializers.UUIDField(required=False)
    ticket_id = serializers.CharField()
    author = serializers.CharField()
    text = serializers.CharField()
    created_at = serializers.DateTimeField(required=False)


class TeamsMessageSerializer(serializers.Serializer):
    """Serializer for Teams messages."""
    id = serializers.CharField()
    channel = serializers.CharField()
    sender = serializers.CharField()
    text = serializers.CharField()
    timestamp = serializers.DateTimeField(required=False)
    likes = serializers.IntegerField(required=False)
    replies = serializers.IntegerField(required=False)


class ActivitySerializer(serializers.Serializer):
    """Serializer for activity feed."""
    id = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    type = serializers.CharField()
    timestamp = serializers.DateTimeField()
    project_id = serializers.CharField(required=False)
