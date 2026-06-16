"""
Django Models for Onboarding_AI Knowledge Base

These models map to the existing PostgreSQL tables.
Using managed = False since tables already exist.
"""

import uuid
import re
from django.db import models
from django.contrib.postgres.fields import ArrayField


class GitCommit(models.Model):
    """Stores git commit information"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sha = models.CharField(max_length=40, unique=True)
    author_name = models.CharField(max_length=255)
    author_email = models.EmailField(max_length=255)
    commit_date = models.DateTimeField()
    message = models.TextField()
    related_tickets = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'git_commits'
        managed = False  # Table already exists
        ordering = ['-commit_date']
    
    def __str__(self):
        return f"{self.sha[:7]} - {self.message[:50]}"
    
    def extract_ticket_references(self):
        """Extract Jira ticket references from commit message"""
        pattern = r'PAY-\d+'
        matches = re.findall(pattern, self.message, re.IGNORECASE)
        return list(set([m.upper() for m in matches]))


class GitCommitFile(models.Model):
    """Stores files changed in each commit"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    commit = models.ForeignKey(
        GitCommit, 
        on_delete=models.CASCADE, 
        related_name='files',
        db_column='commit_id'
    )
    filename = models.CharField(max_length=500)
    additions = models.IntegerField(default=0)
    deletions = models.IntegerField(default=0)
    status = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'git_commit_files'
        managed = False
    
    def __str__(self):
        return f"{self.filename} ({self.status})"


class Meeting(models.Model):
    """Stores meeting metadata and processed content"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500, blank=True, null=True)
    meeting_date = models.DateTimeField(blank=True, null=True)
    raw_vtt_content = models.TextField()
    summary = models.TextField(blank=True, null=True)
    key_decisions = models.TextField(blank=True, null=True)
    action_items = models.TextField(blank=True, null=True)
    participants = models.TextField(blank=True, null=True)
    duration_seconds = models.IntegerField(blank=True, null=True)
    source_filename = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'meetings'
        managed = False
        ordering = ['-meeting_date']
    
    def __str__(self):
        return self.title or f"Meeting {self.id}"
    
    def extract_participants_from_vtt(self):
        """Extract unique speaker names from VTT content"""
        pattern = r'^([A-Za-z\s\']+):'
        lines = self.raw_vtt_content.split('\n')
        speakers = set()
        for line in lines:
            match = re.match(pattern, line.strip())
            if match:
                speaker = match.group(1).strip()
                if not re.match(r'^\d', speaker):
                    speakers.add(speaker)
        return list(speakers)
    
    def extract_ticket_references(self):
        """Extract Jira ticket references from transcript"""
        pattern = r'PAY-\d+'
        matches = re.findall(pattern, self.raw_vtt_content, re.IGNORECASE)
        return list(set([m.upper() for m in matches]))


class JiraTicket(models.Model):
    """Stores Jira ticket information (flat structure)"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue_key = models.CharField(max_length=50, unique=True)
    issue_type = models.CharField(max_length=50)
    summary = models.CharField(max_length=500)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50)
    priority = models.CharField(max_length=50, blank=True, null=True)
    assignee = models.CharField(max_length=255, blank=True, null=True)
    reporter = models.CharField(max_length=255, blank=True, null=True)
    created_date = models.DateTimeField(blank=True, null=True)
    updated_date = models.DateTimeField(blank=True, null=True)
    resolved_date = models.DateTimeField(blank=True, null=True)
    labels = models.TextField(blank=True, null=True)
    epic_link = models.CharField(max_length=50, blank=True, null=True)
    sprint = models.CharField(max_length=100, blank=True, null=True)
    story_points = models.IntegerField(blank=True, null=True)
    comments = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'jira_tickets'
        managed = False
        ordering = ['-created_date']
    
    def __str__(self):
        return f"{self.issue_key}: {self.summary[:50]}"


class ConfluencePage(models.Model):
    """Stores Confluence page content and metadata"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500)
    space = models.CharField(max_length=255, blank=True, null=True)
    author = models.CharField(max_length=255, blank=True, null=True)
    content = models.TextField()
    labels = ArrayField(
        models.CharField(max_length=100),
        blank=True,
        default=list
    )
    version = models.IntegerField(default=1)
    page_created_date = models.DateTimeField(blank=True, null=True)
    page_updated_date = models.DateTimeField(blank=True, null=True)
    source_filename = models.CharField(max_length=255, blank=True, null=True)
    drift_risk = models.CharField(max_length=10, blank=True, null=True)
    last_activity_date = models.DateTimeField(blank=True, null=True)
    confluence_topics = ArrayField(
        models.TextField(),
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'confluence_pages'
        managed = False
        ordering = ['-page_updated_date']
    
    def __str__(self):
        return self.title
    
    def extract_ticket_references(self):
        """Extract Jira ticket references from page content"""
        pattern = r'PAY-\d+'
        matches = re.findall(pattern, self.content, re.IGNORECASE)
        return list(set([m.upper() for m in matches]))


class EntityReference(models.Model):
    """Links entities across different sources"""
    
    SOURCE_TYPE_CHOICES = [
        ('commit', 'Git Commit'),
        ('meeting', 'Meeting'),
        ('jira_ticket', 'Jira Ticket'),
        ('confluence', 'Confluence Page'),
    ]
    
    REFERENCE_TYPE_CHOICES = [
        ('jira_ticket', 'Jira Ticket'),
        ('commit', 'Git Commit'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_type = models.CharField(max_length=50, choices=SOURCE_TYPE_CHOICES)
    source_id = models.UUIDField()
    reference_type = models.CharField(max_length=50, choices=REFERENCE_TYPE_CHOICES)
    reference_id = models.CharField(max_length=100)
    extraction_method = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'entity_references'
        managed = False
        unique_together = ['source_type', 'source_id', 'reference_type', 'reference_id']
    
    def __str__(self):
        return f"{self.source_type}:{self.source_id} -> {self.reference_type}:{self.reference_id}"
    
class Project(models.Model):
    """Groups related tickets, commits, meetings, and pages"""
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='active')
    
    # Linking to Jira
    epic_key = models.CharField(max_length=50, blank=True, null=True)
    jira_project_key = models.CharField(max_length=20, blank=True, null=True)
    
    # Linking to other sources
    github_repo = models.CharField(max_length=255, blank=True, null=True)
    confluence_space_key = models.CharField(max_length=50, blank=True, null=True)
    
    # Dates
    start_date = models.DateField(blank=True, null=True)
    target_end_date = models.DateField(blank=True, null=True)
    actual_end_date = models.DateField(blank=True, null=True)
    
    # Metadata
    owner = models.CharField(max_length=255, blank=True, null=True)
    team_members = models.TextField(blank=True, null=True)  # JSON array
    tags = ArrayField(
        models.CharField(max_length=100),
        blank=True,
        default=list
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'projects'
        managed = False
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


class ProjectEntity(models.Model):
    """Links projects to specific entities"""
    
    ENTITY_TYPE_CHOICES = [
        ('commit', 'Git Commit'),
        ('meeting', 'Meeting'),
        ('jira_ticket', 'Jira Ticket'),
        ('confluence', 'Confluence Page'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='entities',
        db_column='project_id'
    )
    entity_type = models.CharField(max_length=50, choices=ENTITY_TYPE_CHOICES)
    entity_id = models.UUIDField()
    added_manually = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'project_entities'
        managed = False
        unique_together = ['project', 'entity_type', 'entity_id']
    
    def __str__(self):
        return f"{self.project.name} - {self.entity_type}"
    
class Employee(models.Model):
    """Stores team member information"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    email = models.EmailField(max_length=255, blank=True, null=True)
    role = models.CharField(max_length=100, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    source = models.CharField(max_length=50, blank=True, null=True)
    jira_account_id = models.CharField(max_length=255, blank=True, null=True)
    github_username = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'employees'
        managed = False
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
class Sprint(models.Model):
    """Stores sprint information"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint_number = models.IntegerField()
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    goal = models.TextField(blank=True, null=True)
    project = models.ForeignKey(
        'Project', 
        on_delete=models.CASCADE, 
        related_name='sprints',
        blank=True, 
        null=True
    )
    status = models.CharField(max_length=50, default='planned')  # planned, active, completed
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'sprints'
        managed = False
        ordering = ['sprint_number']
        unique_together = ['sprint_number', 'project']
    
    def __str__(self):
        return f"{self.name} (Sprint {self.sprint_number})"


class SprintTicket(models.Model):
    """Links sprints to jira tickets"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sprint = models.ForeignKey(
        Sprint, 
        on_delete=models.CASCADE, 
        related_name='sprint_tickets'
    )
    ticket = models.ForeignKey(
        'JiraTicket', 
        on_delete=models.CASCADE, 
        related_name='sprint_assignments'
    )
    added_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'sprint_tickets'
        managed = False
        unique_together = ['sprint', 'ticket']
    
    def __str__(self):
        return f"{self.sprint.name} - {self.ticket.issue_key}"

class Decision(models.Model):
    """
    Stores decisions extracted from meetings, confluence, jira, and commits.
    This is the unified decision timeline.
    """
    
    # Status choices
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('superseded', 'Superseded'),
        ('reversed', 'Reversed'),
        ('proposed', 'Proposed'),
        ('duplicate', 'Duplicate'),
    ]
    
    # Category choices
    CATEGORY_CHOICES = [
        ('architecture', 'Architecture'),
        ('technology', 'Technology'),
        ('process', 'Process'),
        ('design', 'Design'),
        ('infrastructure', 'Infrastructure'),
        ('security', 'Security'),
        ('other', 'Other'),
    ]
    
    # Source type choices
    SOURCE_TYPE_CHOICES = [
        ('meeting', 'Meeting'),
        ('confluence', 'Confluence'),
        ('jira', 'Jira'),
        ('git_commit', 'Git Commit'),
    ]
    
    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Core decision info
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True, null=True)
    decision_date = models.DateField()
    
    # Context and reasoning (THE "WHY")
    rationale = models.TextField(blank=True, null=True)
    alternatives_considered = models.TextField(blank=True, null=True)
    impact = models.TextField(blank=True, null=True)
    
    # People
    decided_by = ArrayField(
        models.CharField(max_length=255),
        blank=True,
        null=True
    )
    
    # Source tracking
    source_type = models.CharField(max_length=50, choices=SOURCE_TYPE_CHOICES)
    source_id = models.UUIDField(blank=True, null=True)
    source_title = models.CharField(max_length=500, blank=True, null=True)
    
    # Relationships
    related_tickets = ArrayField(
        models.CharField(max_length=50),
        blank=True,
        null=True
    )
    related_decisions = ArrayField(
        models.UUIDField(),
        blank=True,
        null=True
    )
    
    # Categorization
    category = models.CharField(
        max_length=100, 
        choices=CATEGORY_CHOICES,
        blank=True, 
        null=True
    )
    tags = ArrayField(
        models.CharField(max_length=100),
        blank=True,
        null=True
    )
    
    # Lifecycle
    status = models.CharField(
        max_length=50, 
        choices=STATUS_CHOICES,
        default='active'
    )
    superseded_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='supersedes_decisions',
        db_column='superseded_by'
    )
    supersedes = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='superseded_by_decisions',
        db_column='supersedes'
    )
    
    # Metadata
    confidence_score = models.FloatField(blank=True, null=True)
    extraction_notes = models.TextField(blank=True, null=True)

    # Drift detection
    last_reinforced_at = models.DateTimeField(blank=True, null=True)
    drift_risk = models.CharField(
        max_length=10,
        choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        blank=True,
        null=True
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'decisions'
        managed = False  # Table created via SQL
        ordering = ['-decision_date']
    
    def __str__(self):
        return f"{self.decision_date}: {self.title[:50]}"


class DecisionConflict(models.Model):
    """
    Records a detected conflict between two active decisions.
    Populated by check_conflicts.py.
    """

    CONFLICT_TYPE_CHOICES = [
        ('direct',   'Direct'),    # mutually exclusive choices (e.g. Material UI vs Tailwind)
        ('indirect', 'Indirect'),  # tension that may cause problems (e.g. two DB access layers)
        ('potential','Potential'), # flagged for human review; LLM uncertain
    ]

    SEVERITY_CHOICES = [
        ('low',    'Low'),
        ('medium', 'Medium'),
        ('high',   'High'),
    ]

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    decision_a    = models.ForeignKey(
        Decision, on_delete=models.CASCADE, related_name='conflicts_as_a', db_column='decision_a_id'
    )
    decision_b    = models.ForeignKey(
        Decision, on_delete=models.CASCADE, related_name='conflicts_as_b', db_column='decision_b_id'
    )
    conflict_type = models.CharField(max_length=50, choices=CONFLICT_TYPE_CHOICES)
    explanation   = models.TextField(blank=True, null=True)
    severity      = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    detected_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'decision_conflicts'
        managed  = False
        unique_together = [('decision_a', 'decision_b')]

    def __str__(self):
        return f"[{self.severity.upper()}] {self.decision_a.title[:40]} ↔ {self.decision_b.title[:40]}"
