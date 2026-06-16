from django.db.models import Q
from rest_framework import generics, views
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, inline_serializer
from rest_framework import serializers as drf_serializers
import uuid

from knowledge_base.models import (
    GitCommit, JiraTicket, ConfluencePage,
    Meeting, Project, EntityReference,
    Employee, Sprint, SprintTicket, Decision,
)
from .serializers import (
    GitCommitSerializer,
    JiraTicketSerializer,
    ConfluencePageListSerializer,
    ConfluencePageSerializer,
    MeetingListSerializer,
    MeetingDetailSerializer,
    ProjectSerializer,
    EntityReferenceSerializer,
    EmployeeSerializer,
    SprintSerializer,
    SprintTicketSerializer,
    DecisionSerializer,
    SprintOutcomeSerializer,
)
from .ingestion import (
    run_github_ingest,
    run_jira_ingest,
    run_confluence_ingest,
    run_meeting_ingest,
)


# ── Reusable inline serializers for schema documentation ─────────────────────

_ErrorSerializer = inline_serializer('Error', fields={
    'error': drf_serializers.CharField(),
})

_DeleteResponseSerializer = inline_serializer('DeleteResponse', fields={
    'deleted': drf_serializers.BooleanField(),
    'entity_type': drf_serializers.CharField(),
    'id': drf_serializers.CharField(),
})

_IngestResultSerializer = inline_serializer('IngestResult', fields={
    'status': drf_serializers.CharField(),
    'created': drf_serializers.IntegerField(required=False),
    'updated': drf_serializers.IntegerField(required=False),
    'skipped': drf_serializers.IntegerField(required=False),
})

_SearchResultSerializer = inline_serializer('SearchResult', fields={
    'query': drf_serializers.CharField(),
    'commits': GitCommitSerializer(many=True),
    'tickets': JiraTicketSerializer(many=True),
    'pages': ConfluencePageListSerializer(many=True),
    'meetings': MeetingListSerializer(many=True),
})

_TicketContextSerializer = inline_serializer('TicketContext', fields={
    'ticket': JiraTicketSerializer(),
    'linked_commits': GitCommitSerializer(many=True),
    'linked_pages': ConfluencePageListSerializer(many=True),
    'linked_meetings': MeetingListSerializer(many=True),
})


# ── Test ─────────────────────────────────────────────────────────────────────

class HelloPreetyView(APIView):
    @extend_schema(
        tags=['Test'],
        summary='Health check',
        description='Simple endpoint to verify the API is running.',
        responses={200: inline_serializer('HelloResponse', fields={
            'message': drf_serializers.CharField(),
        })},
    )
    def get(self, request):
        return Response({"message": "hello preety"})



# ── Commits ──────────────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(
        tags=['Commits'],
        summary='List all commits',
        description='Returns every git commit stored in the knowledge base, newest first. Includes changed files. Optional: filter by project_id.',
        parameters=[
            OpenApiParameter(
                name='project_id', type=str, location=OpenApiParameter.QUERY,
                required=False, description='Filter commits by project UUID.',
            ),
        ],
    ),
)
class CommitListView(generics.ListAPIView):
    serializer_class = GitCommitSerializer
    
    def get_queryset(self):
        qs = GitCommit.objects.prefetch_related('files').all()
        project_id = self.request.query_params.get('project_id')
        if project_id:
            # Filter by project via ProjectEntity
            from knowledge_base.models import ProjectEntity
            commit_ids = ProjectEntity.objects.filter(
                project_id=project_id,
                entity_type='commit'
            ).values_list('entity_id', flat=True)
            qs = qs.filter(id__in=commit_ids)
        return qs


@extend_schema_view(
    get=extend_schema(
        tags=['Commits'],
        summary='Get commit by SHA',
        description='Retrieve a single git commit and its changed files by full SHA.',
    ),
)
class CommitDetailView(generics.RetrieveAPIView):
    serializer_class = GitCommitSerializer
    queryset = GitCommit.objects.prefetch_related('files').all()
    lookup_field = 'sha'


# ── Tickets ───────────────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(
        tags=['Tickets'],
        summary='List all tickets',
        description='Returns every Jira ticket in the knowledge base. Optional: filter by project_id.',
        parameters=[
            OpenApiParameter(
                name='project_id', type=str, location=OpenApiParameter.QUERY,
                required=False, description='Filter tickets by project UUID.',
            ),
        ],
    ),
)
class TicketListView(generics.ListAPIView):
    serializer_class = JiraTicketSerializer
    
    def get_queryset(self):
        qs = JiraTicket.objects.all()
        project_id = self.request.query_params.get('project_id')
        if project_id and project_id != 'all':
            # Filter by project via ProjectEntity
            from knowledge_base.models import ProjectEntity
            ticket_ids = ProjectEntity.objects.filter(
                project_id=project_id,
                entity_type='jira_ticket'
            ).values_list('entity_id', flat=True)
            qs = qs.filter(id__in=ticket_ids)
        return qs


@extend_schema_view(
    get=extend_schema(
        tags=['Tickets'],
        summary='Get ticket by issue key',
        description='Retrieve a single Jira ticket by its issue key (e.g. PAY-123).',
    ),
)
class TicketDetailView(generics.RetrieveAPIView):
    serializer_class = JiraTicketSerializer
    queryset = JiraTicket.objects.all()
    lookup_field = 'issue_key'


class TicketContextView(views.APIView):
    """Returns a ticket plus all linked commits, pages, and meetings via entity_references."""

    @extend_schema(
        tags=['Tickets'],
        summary='Get ticket with linked context',
        description=(
            'Returns the ticket together with all commits, Confluence pages, '
            'and meetings linked to it through entity references.'
        ),
        responses={200: _TicketContextSerializer},
    )
    def get(self, request, issue_key):
        ticket = generics.get_object_or_404(JiraTicket, issue_key=issue_key)

        # EntityReferences where this ticket is the reference target
        refs = EntityReference.objects.filter(
            reference_type='jira_ticket',
            reference_id=issue_key,
        )

        commit_ids = [r.source_id for r in refs if r.source_type == 'commit']
        meeting_ids = [r.source_id for r in refs if r.source_type == 'meeting']
        page_ids = [r.source_id for r in refs if r.source_type == 'confluence']

        from .serializers import GitCommitSerializer, MeetingListSerializer, ConfluencePageListSerializer
        return Response({
            'ticket': JiraTicketSerializer(ticket).data,
            'linked_commits': GitCommitSerializer(
                GitCommit.objects.filter(id__in=commit_ids).prefetch_related('files'),
                many=True,
            ).data,
            'linked_pages': ConfluencePageListSerializer(
                ConfluencePage.objects.filter(id__in=page_ids),
                many=True,
            ).data,
            'linked_meetings': MeetingListSerializer(
                Meeting.objects.filter(id__in=meeting_ids),
                many=True,
            ).data,
        })


# ── Confluence Pages ──────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(
        tags=['Pages'],
        summary='List all Confluence pages',
        description='Returns a summary list of every Confluence page in the knowledge base.',
    ),
)
class PageListView(generics.ListAPIView):
    serializer_class = ConfluencePageListSerializer
    queryset = ConfluencePage.objects.all()


@extend_schema_view(
    get=extend_schema(
        tags=['Pages'],
        summary='Get Confluence page by ID',
        description='Retrieve a single Confluence page with full content.',
    ),
)
class PageDetailView(generics.RetrieveAPIView):
    serializer_class = ConfluencePageSerializer
    queryset = ConfluencePage.objects.all()


# ── Meetings ──────────────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(
        tags=['Meetings'],
        summary='List all meetings',
        description=(
            'Returns meetings with full transcript. '
            'Optionally filter by exact date using `?date=YYYY-MM-DD` or by project using `?project_id=UUID`.'
        ),
        parameters=[
            OpenApiParameter(
                name='date', type=str, location=OpenApiParameter.QUERY,
                required=False, description='Filter by meeting date (YYYY-MM-DD).',
            ),
            OpenApiParameter(
                name='project_id', type=str, location=OpenApiParameter.QUERY,
                required=False, description='Filter meetings by project UUID.',
            ),
        ],
    ),
)
class MeetingListView(generics.ListAPIView):
    serializer_class = MeetingDetailSerializer

    def get_queryset(self):
        qs = Meeting.objects.all()
        date = self.request.query_params.get('date')
        project_id = self.request.query_params.get('project_id')
        
        if date:
            qs = qs.filter(meeting_date__date=date)
        
        if project_id:
            # Filter by project via ProjectEntity
            from knowledge_base.models import ProjectEntity
            meeting_ids = ProjectEntity.objects.filter(
                project_id=project_id,
                entity_type='meeting'
            ).values_list('entity_id', flat=True)
            qs = qs.filter(id__in=meeting_ids)
        
        return qs


@extend_schema_view(
    get=extend_schema(
        tags=['Meetings'],
        summary='Get meeting by ID',
        description='Retrieve full meeting details including raw VTT content.',
    ),
)
class MeetingDetailView(generics.RetrieveAPIView):
    serializer_class = MeetingDetailSerializer
    queryset = Meeting.objects.all()


# ── Projects ──────────────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(
        tags=['Projects'],
        summary='List all projects',
        description='Returns every project with its linked entities.',
    ),
)
class ProjectListView(generics.ListAPIView):
    serializer_class = ProjectSerializer
    queryset = Project.objects.prefetch_related('entities').all()


@extend_schema_view(
    get=extend_schema(
        tags=['Projects'],
        summary='Get project by ID',
        description='Retrieve a single project with all linked entities.',
    ),
)
class ProjectDetailView(generics.RetrieveAPIView):
    serializer_class = ProjectSerializer
    queryset = Project.objects.prefetch_related('entities').all()


class ProjectAddMemberView(APIView):
    """Add a team member to a project's team_members list."""

    @extend_schema(
        tags=['Projects'],
        summary='Add a member to a project team',
        description='Appends a name to the project\'s team_members list if not already present.',
        request=inline_serializer('AddMemberRequest', fields={
            'name': drf_serializers.CharField(),
        }),
        responses={
            200: inline_serializer('AddMemberResponse', fields={
                'status': drf_serializers.CharField(),
                'team_members': drf_serializers.ListField(child=drf_serializers.CharField()),
            }),
            404: _ErrorSerializer,
        },
    )
    def post(self, request, pk):
        import json as _json
        try:
            project = Project.objects.get(pk=pk)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=404)

        name = request.data.get('name', '').strip()
        if not name:
            return Response({'error': 'name is required'}, status=400)

        # Parse existing team_members
        members = []
        if project.team_members:
            try:
                members = _json.loads(project.team_members)
                if not isinstance(members, list):
                    members = []
            except (_json.JSONDecodeError, TypeError):
                members = []

        # Add only if not already present (case-insensitive check)
        if not any(m.lower() == name.lower() for m in members):
            members.append(name)
            project.team_members = _json.dumps(members)
            project.save(update_fields=['team_members'])

        return Response({'status': 'ok', 'team_members': members})


# ── Search ────────────────────────────────────────────────────────────────────

class SearchView(views.APIView):
    """Full-text search across all entity types."""

    @extend_schema(
        tags=['Search'],
        summary='Search across all entities',
        description=(
            'Searches commit messages, ticket summaries/descriptions, '
            'page titles/content, and meeting titles for the given query string.'
        ),
        parameters=[
            OpenApiParameter(
                name='q',
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description='Search query string.',
            ),
        ],
        responses={
            200: _SearchResultSerializer,
            400: _ErrorSerializer,
        },
    )
    def get(self, request):
        q = request.query_params.get('q', '').strip()
        if not q:
            return Response({'error': 'Query parameter "q" is required.'}, status=400)

        commits = GitCommit.objects.filter(message__icontains=q).prefetch_related('files')
        tickets = JiraTicket.objects.filter(
            Q(summary__icontains=q) | Q(description__icontains=q)
        )
        pages = ConfluencePage.objects.filter(
            Q(title__icontains=q) | Q(content__icontains=q)
        )
        meetings = Meeting.objects.filter(title__icontains=q)

        return Response({
            'query': q,
            'commits': GitCommitSerializer(commits, many=True).data,
            'tickets': JiraTicketSerializer(tickets, many=True).data,
            'pages': ConfluencePageListSerializer(pages, many=True).data,
            'meetings': MeetingListSerializer(meetings, many=True).data,
        })


# ── Ingest ────────────────────────────────────────────────────────────────────

class IngestGithubView(APIView):
    @extend_schema(
        tags=['Ingestion'],
        summary='Ingest GitHub commits',
        description='Pulls commits from the configured GitHub repo and stores them in the knowledge base.',
        request=None,
        responses={200: _IngestResultSerializer, 400: _ErrorSerializer, 500: _ErrorSerializer},
    )
    def post(self, request):
        try:
            result = run_github_ingest()
            return Response(result)
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class IngestJiraView(APIView):
    @extend_schema(
        tags=['Ingestion'],
        summary='Ingest Jira tickets',
        description='Pulls tickets from the configured Jira project and stores them in the knowledge base.',
        request=None,
        responses={200: _IngestResultSerializer, 400: _ErrorSerializer, 500: _ErrorSerializer},
    )
    def post(self, request):
        try:
            result = run_jira_ingest()
            return Response(result)
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class IngestConfluenceView(APIView):
    @extend_schema(
        tags=['Ingestion'],
        summary='Ingest Confluence pages',
        description='Pulls pages from the configured Confluence space and stores them in the knowledge base.',
        request=None,
        responses={200: _IngestResultSerializer, 400: _ErrorSerializer, 500: _ErrorSerializer},
    )
    def post(self, request):
        try:
            result = run_confluence_ingest()
            return Response(result)
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class IngestMeetingView(APIView):
    @extend_schema(
        tags=['Ingestion'],
        summary='Ingest meeting transcript',
        description='Upload a `.vtt` file to parse and store a meeting transcript. Send as multipart/form-data with key `file`.',
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'file': {'type': 'string', 'format': 'binary', 'description': 'A .vtt transcript file'},
                },
                'required': ['file'],
            },
        },
        responses={200: _IngestResultSerializer, 400: _ErrorSerializer, 500: _ErrorSerializer},
    )
    def post(self, request):
        vtt_file = request.FILES.get('file')
        if not vtt_file:
            return Response(
                {'error': 'No file uploaded. Send a .vtt file with key "file".'},
                status=400,
            )
        if not vtt_file.name.endswith('.vtt'):
            return Response({'error': 'File must be a .vtt file.'}, status=400)
        try:
            vtt_content = vtt_file.read().decode('utf-8')
            result = run_meeting_ingest(vtt_content, vtt_file.name)
            return Response(result)
        except Exception as e:
            return Response({'error': str(e)}, status=500)


# ── Sprint Outcomes ───────────────────────────────────────────────────────────

class SprintTicketsOutcomeView(views.APIView):
    """GET /api/sprints/<sprint_number>/tickets/ — tickets in a sprint with completion status."""

    @extend_schema(
        tags=['Sprints'],
        summary='Get sprint ticket outcomes',
        description=(
            'Returns all Jira tickets in a sprint with completion status. '
            'Each ticket includes `is_completed`, `teammates`, and `teammates_count`. '
            'Also returns summary counts: total, completed, pending.'
        ),
        responses={
            200: SprintOutcomeSerializer,
            404: _ErrorSerializer,
        },
    )
    def get(self, request, sprint_number):
        # Support optional project_id query param (sprint_number alone may not be unique)
        project_id = request.query_params.get('project_id')
        if project_id:
            sprint = generics.get_object_or_404(Sprint, sprint_number=sprint_number, project_id=project_id)
        else:
            # Fall back to first sprint with this number if no project specified
            sprint = generics.get_object_or_404(Sprint, sprint_number=sprint_number)
        return Response(SprintOutcomeSerializer(sprint).data)


class SprintMeetingsView(views.APIView):
    """GET /api/sprints/<sprint_number>/meetings/ — meetings that happened during a sprint."""

    @extend_schema(
        tags=['Sprints'],
        summary='Get meetings during a sprint',
        description=(
            'Returns all meeting transcripts where the meeting date falls within '
            'the sprint\'s start and end dates.'
        ),
        responses={
            200: MeetingDetailSerializer(many=True),
            404: _ErrorSerializer,
        },
    )
    def get(self, request, sprint_number):
        # Support optional project_id query param (sprint_number alone may not be unique)
        project_id = request.query_params.get('project_id')
        if project_id:
            sprint = generics.get_object_or_404(Sprint, sprint_number=sprint_number, project_id=project_id)
        else:
            # Fall back to first sprint with this number if no project specified
            sprint = generics.get_object_or_404(Sprint, sprint_number=sprint_number)
        meetings = Meeting.objects.filter(
            meeting_date__date__gte=sprint.start_date,
            meeting_date__date__lte=sprint.end_date,
        )
        return Response(MeetingDetailSerializer(meetings, many=True).data)


# ── Register (create Employee) ───────────────────────────────────────────────

class RegisterView(APIView):
    """Register a new user by creating an Employee record."""

    @extend_schema(
        tags=['Auth'],
        summary='Register a new user',
        description='Creates an Employee record with name, email, role, and department.',
        request=inline_serializer('RegisterRequest', fields={
            'name': drf_serializers.CharField(),
            'email': drf_serializers.EmailField(),
            'role': drf_serializers.CharField(required=False),
            'department': drf_serializers.CharField(required=False),
        }),
        responses={
            201: EmployeeSerializer,
            400: _ErrorSerializer,
        },
    )
    def post(self, request):
        name = request.data.get('name', '').strip()
        email = request.data.get('email', '').strip()
        role = request.data.get('role', '').strip()
        department = request.data.get('department', '').strip()

        if not name:
            return Response({'error': 'Name is required.'}, status=400)
        if not email:
            return Response({'error': 'Email is required.'}, status=400)

        # Check if an employee with this email already exists
        existing = Employee.objects.filter(email__iexact=email).first()
        if existing:
            # Update the existing record with any new info
            if role:
                existing.role = role
            if department:
                existing.department = department
            if name:
                existing.name = name
            existing.is_active = True
            existing.source = 'registration'
            existing.save()
            serializer = EmployeeSerializer(existing)
            return Response(serializer.data, status=200)

        # Also check by name
        existing_name = Employee.objects.filter(name__iexact=name).first()
        if existing_name:
            if role:
                existing_name.role = role
            if department:
                existing_name.department = department
            if email:
                existing_name.email = email
            existing_name.is_active = True
            existing_name.source = 'registration'
            existing_name.save()
            serializer = EmployeeSerializer(existing_name)
            return Response(serializer.data, status=200)

        # Create new employee
        employee = Employee.objects.create(
            name=name,
            email=email,
            role=role or None,
            department=department or None,
            source='registration',
            is_active=True,
        )
        serializer = EmployeeSerializer(employee)
        return Response(serializer.data, status=201)


# ── Employees ────────────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(
        tags=['Employees'],
        summary='List all employees',
        description='Returns all team members stored in the knowledge base.',
    ),
)
class EmployeeListView(generics.ListAPIView):
    serializer_class = EmployeeSerializer
    queryset = Employee.objects.all()


@extend_schema_view(
    get=extend_schema(
        tags=['Employees'],
        summary='Get employee by ID',
        description='Retrieve a single employee record by UUID.',
    ),
)
class EmployeeDetailView(generics.RetrieveAPIView):
    serializer_class = EmployeeSerializer
    queryset = Employee.objects.all()


# ── Sprints ───────────────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(
        tags=['Sprints'],
        summary='List all sprints',
        description='Returns all sprints with their linked tickets. Optional: filter by project_id.',
        parameters=[
            OpenApiParameter(
                name='project_id', type=str, location=OpenApiParameter.QUERY,
                required=False, description='Filter sprints by project UUID.',
            ),
        ],
    ),
)
class SprintListView(generics.ListAPIView):
    serializer_class = SprintSerializer
    
    def get_queryset(self):
        qs = Sprint.objects.prefetch_related('sprint_tickets').all()
        project_id = self.request.query_params.get('project_id')
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs


@extend_schema_view(
    get=extend_schema(
        tags=['Sprints'],
        summary='Get sprint by sprint number',
        description='Retrieve a single sprint with all its tickets by sprint number (e.g. 1, 2, 3).',
    ),
)
class SprintDetailView(generics.RetrieveAPIView):
    serializer_class = SprintSerializer
    queryset = Sprint.objects.prefetch_related('sprint_tickets').all()
    lookup_field = 'sprint_number'


# ── Decisions ─────────────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(
        tags=['Decisions'],
        summary='List all decisions',
        description='Returns the unified decision timeline across meetings, Confluence, Jira, and commits.',
        parameters=[
            OpenApiParameter(name='category', type=str, location=OpenApiParameter.QUERY,
                             required=False, description='Filter by category (e.g. architecture, technology).'),
            OpenApiParameter(name='source_type', type=str, location=OpenApiParameter.QUERY,
                             required=False, description='Filter by source (meeting, confluence, jira, git_commit).'),
        ],
    ),
)
class DecisionListView(generics.ListAPIView):
    serializer_class = DecisionSerializer

    def get_queryset(self):
        qs = Decision.objects.all()
        category = self.request.query_params.get('category')
        source_type = self.request.query_params.get('source_type')
        if category:
            qs = qs.filter(category=category)
        if source_type:
            qs = qs.filter(source_type=source_type)
        return qs


@extend_schema_view(
    get=extend_schema(
        tags=['Decisions'],
        summary='Get decision by ID',
        description='Retrieve a single decision record by UUID.',
    ),
)
class DecisionDetailView(generics.RetrieveAPIView):
    serializer_class = DecisionSerializer
    queryset = Decision.objects.all()


# ── Delete ────────────────────────────────────────────────────────────────────

ENTITY_MAP = {
    'commits':   (GitCommit,      'sha'),
    'tickets':   (JiraTicket,     'issue_key'),
    'pages':     (ConfluencePage, 'pk'),
    'meetings':  (Meeting,        'pk'),
    'projects':  (Project,        'pk'),
    'employees': (Employee,       'pk'),
    'sprints':   (Sprint,         'pk'),
    'decisions': (Decision,       'pk'),
}

# ── Chat ─────────────────────────────────────────────────────────────────────

# In-memory store of OnboardingChatbot instances keyed by conversation_id.
# Each conversation gets its own bot instance so history is preserved per session.
_chat_sessions: dict = {}

_ChatRequestSerializer = inline_serializer('ChatRequest', fields={
    'query': drf_serializers.CharField(),
    'conversation_id': drf_serializers.CharField(required=False),
})

_ChatResponseSerializer = inline_serializer('ChatResponse', fields={
    'answer': drf_serializers.CharField(),
    'intent': drf_serializers.CharField(),
    'confidence': drf_serializers.FloatField(),
    'sources': drf_serializers.ListField(child=drf_serializers.CharField()),
    'conversation_id': drf_serializers.CharField(),
    'turn': drf_serializers.IntegerField(),
})


class ChatView(APIView):
    """POST /api/chat/ — send a query to the AI chatbot and get a response."""

    @extend_schema(
        tags=['Chat'],
        summary='Chat with the AI assistant',
        description=(
            'Send a natural-language query to the onboarding AI chatbot. '
            'The bot classifies intent, retrieves relevant records from the knowledge base, '
            'builds context, and generates a response via Groq. '
            'Pass `conversation_id` from a previous response to continue an existing conversation '
            '(the bot remembers prior turns and resolves references like "it" or "that decision"). '
            'Omit `conversation_id` to start a fresh session.'
        ),
        request=_ChatRequestSerializer,
        responses={
            200: _ChatResponseSerializer,
            400: _ErrorSerializer,
            503: _ErrorSerializer,
        },
    )
    def post(self, request):
        query = (request.data.get('query') or '').strip()
        if not query:
            return Response({'error': 'Field "query" is required.'}, status=400)

        conversation_id = request.data.get('conversation_id') or str(uuid.uuid4())

        # Get or create a chatbot instance for this conversation
        if conversation_id not in _chat_sessions:
            try:
                from chatbot.main import OnboardingChatbot
                _chat_sessions[conversation_id] = OnboardingChatbot()
            except Exception as e:
                return Response(
                    {'error': f'Failed to initialize chatbot: {str(e)}'},
                    status=503,
                )

        bot = _chat_sessions[conversation_id]

        try:
            response = bot.chat(query)
        except Exception as e:
            return Response({'error': f'Chatbot error: {str(e)}'}, status=503)

        return Response({
            'answer': response.answer,
            'intent': response.intent,
            'confidence': response.confidence,
            'sources': response.sources,
            'conversation_id': conversation_id,
            'turn': response.conversation_turn,
        })


# ── Query (Alias for Chat) ─────────────────────────────────────────────────────

class QueryView(APIView):
    """POST /api/query/ — alias for chat endpoint for extension compatibility."""

    @extend_schema(
        tags=['Chat'],
        summary='Chat with the AI assistant (extension endpoint)',
        description=(
            'Alias for the chat endpoint. Send a natural-language query to the chatbot. '
            'Pass `conversation_id` to continue an existing conversation, omit it to start fresh.'
        ),
        request=_ChatRequestSerializer,
        responses={
            200: _ChatResponseSerializer,
            400: _ErrorSerializer,
            503: _ErrorSerializer,
        },
    )
    def post(self, request):
        query = (request.data.get('query') or '').strip()
        if not query:
            return Response({'error': 'Field "query" is required.'}, status=400)

        conversation_id = request.data.get('conversation_id') or str(uuid.uuid4())

        # Get or create a chatbot instance for this conversation
        if conversation_id not in _chat_sessions:
            try:
                from chatbot.main import OnboardingChatbot
                _chat_sessions[conversation_id] = OnboardingChatbot()
            except Exception as e:
                return Response(
                    {'error': f'Failed to initialize chatbot: {str(e)}'},
                    status=503,
                )

        bot = _chat_sessions[conversation_id]

        try:
            response = bot.chat(query)
        except Exception as e:
            return Response({'error': f'Chatbot error: {str(e)}'}, status=503)

        return Response({
            'answer': response.answer,
            'intent': response.intent,
            'confidence': response.confidence,
            'sources': response.sources,
            'conversation_id': conversation_id,
            'turn': response.conversation_turn,
        })


# ── Ticket Comments ───────────────────────────────────────────────────────────

class TicketCommentsView(APIView):
    """POST /api/tickets/<issue_key>/comments/ — add a comment to a ticket."""

    @extend_schema(
        tags=['Tickets'],
        summary='Add comment to ticket',
        description='Add a comment to a Jira ticket. Stores in the ticket comments field.',
        request=inline_serializer('AddCommentRequest', fields={
            'text': drf_serializers.CharField(),
            'author': drf_serializers.CharField(required=False),
        }),
        responses={
            201: inline_serializer('TicketComment', fields={
                'id': drf_serializers.UUIDField(),
                'ticket_id': drf_serializers.CharField(),
                'author': drf_serializers.CharField(),
                'text': drf_serializers.CharField(),
                'created_at': drf_serializers.DateTimeField(),
            }),
            400: _ErrorSerializer,
            404: _ErrorSerializer,
        },
    )
    def post(self, request, issue_key):
        ticket = generics.get_object_or_404(JiraTicket, issue_key=issue_key)
        
        text = request.data.get('text', '').strip()
        author = request.data.get('author', 'Unknown').strip()
        
        if not text:
            return Response({'error': 'Comment text is required.'}, status=400)
        
        # Append comment to existing comments
        from datetime import datetime
        comment_entry = f"[{datetime.now().isoformat()}] {author}: {text}"
        
        if ticket.comments:
            ticket.comments += f"\n\n{comment_entry}"
        else:
            ticket.comments = comment_entry
        
        ticket.save()
        
        return Response({
            'id': uuid.uuid4(),
            'ticket_id': issue_key,
            'author': author,
            'text': text,
            'created_at': datetime.now().isoformat(),
        }, status=201)


# ── Teams Messages ─────────────────────────────────────────────────────────────

class TeamsMessagesView(generics.ListAPIView):
    """GET /api/teams/messages/ — list Teams messages (placeholder for Teams integration)."""

    @extend_schema(
        tags=['Teams'],
        summary='List Teams messages',
        description='Get Teams messages for a project. Optional: filter by project_id.',
        parameters=[
            OpenApiParameter(
                name='project_id', type=str, location=OpenApiParameter.QUERY,
                required=False, description='Filter messages by project UUID.',
            ),
            OpenApiParameter(
                name='channel', type=str, location=OpenApiParameter.QUERY,
                required=False, description='Filter messages by channel name.',
            ),
        ],
        responses={
            200: inline_serializer('TeamsMessageList', fields={
                'id': drf_serializers.CharField(),
                'channel': drf_serializers.CharField(),
                'sender': drf_serializers.CharField(),
                'text': drf_serializers.CharField(),
                'timestamp': drf_serializers.DateTimeField(required=False),
                'likes': drf_serializers.IntegerField(required=False),
                'replies': drf_serializers.IntegerField(required=False),
            }, many=True),
        },
    )
    def get(self, request):
        # Placeholder implementation - returns sample data
        # In production, this would integrate with Microsoft Teams API
        project_id = request.query_params.get('project_id')
        channel = request.query_params.get('channel', '')
        
        # Sample Teams messages
        messages = [
            {
                'id': 'msg-1',
                'channel': '#general',
                'sender': 'John Doe',
                'text': 'Sprint 3 planning meeting will be at 2 PM today.',
                'timestamp': '2026-05-11T10:30:00Z',
                'likes': 2,
                'replies': 1,
            },
            {
                'id': 'msg-2',
                'channel': '#engineering',
                'sender': 'Jane Smith',
                'text': 'PR #234 is ready for review - OAuth implementation',
                'timestamp': '2026-05-11T09:15:00Z',
                'likes': 5,
                'replies': 3,
            },
            {
                'id': 'msg-3',
                'channel': '#product',
                'sender': 'Mike Wilson',
                'text': 'Dashboard UX improvements deployed to staging',
                'timestamp': '2026-05-10T16:45:00Z',
                'likes': 8,
                'replies': 2,
            },
        ]
        
        # Filter by channel if provided
        if channel:
            messages = [m for m in messages if channel.lower() in m['channel'].lower()]
        
        return Response(messages)


# ── Activity ───────────────────────────────────────────────────────────────────

class ActivityView(generics.ListAPIView):
    """GET /api/activity/ — get recent project activity."""

    @extend_schema(
        tags=['Activity'],
        summary='Get recent activity',
        description='Get recent project activity including commits, ticket changes, meetings, etc. Optional: filter by project_id.',
        parameters=[
            OpenApiParameter(
                name='project_id', type=str, location=OpenApiParameter.QUERY,
                required=False, description='Filter activity by project UUID.',
            ),
            OpenApiParameter(
                name='limit', type=int, location=OpenApiParameter.QUERY,
                required=False, description='Maximum number of activities to return (default 20).',
            ),
        ],
        responses={
            200: inline_serializer('ActivityList', fields={
                'id': drf_serializers.CharField(),
                'title': drf_serializers.CharField(),
                'description': drf_serializers.CharField(),
                'type': drf_serializers.CharField(),
                'timestamp': drf_serializers.DateTimeField(),
                'project_id': drf_serializers.CharField(required=False),
            }, many=True),
        },
    )
    def get(self, request):
        project_id = request.query_params.get('project_id')
        limit = int(request.query_params.get('limit', 20))
        
        activities = []
        
        # Get recent commits
        commits = GitCommit.objects.all().order_by('-commit_date')[:5]
        for commit in commits:
            activities.append({
                'id': commit.sha[:8],
                'title': 'Git Commit',
                'description': commit.message[:100],
                'type': 'commit',
                'timestamp': commit.commit_date.isoformat() if commit.commit_date else None,
                'project_id': project_id or 'all',
            })
        
        # Get recent ticket updates
        tickets = JiraTicket.objects.all().order_by('-updated_date')[:5]
        for ticket in tickets:
            activities.append({
                'id': ticket.issue_key,
                'title': f'Ticket Update: {ticket.issue_key}',
                'description': ticket.summary[:100],
                'type': 'ticket',
                'timestamp': (ticket.updated_date or ticket.created_date).isoformat() if (ticket.updated_date or ticket.created_date) else None,
                'project_id': project_id or 'all',
            })
        
        # Get recent meetings
        meetings = Meeting.objects.all().order_by('-meeting_date')[:3]
        for meeting in meetings:
            activities.append({
                'id': str(meeting.id),
                'title': 'Meeting',
                'description': meeting.title or f'Meeting {meeting.id}',
                'type': 'meeting',
                'timestamp': (meeting.meeting_date or meeting.created_at).isoformat() if (meeting.meeting_date or meeting.created_at) else None,
                'project_id': project_id or 'all',
            })
        
        # Sort by timestamp, newest first
        activities = [a for a in activities if a['timestamp'] is not None]
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Return limited results
        return Response(activities[:limit])


# ── Ticket Management ──────────────────────────────────────────────────────────

class UpdateTicketStatusView(APIView):
    """PATCH /api/tickets/<issue_key>/status/ — update ticket status and assignee."""

    @extend_schema(
        tags=['Tickets'],
        summary='Update ticket status',
        description='Update the status and/or assignee of a Jira ticket.',
        request=inline_serializer('UpdateTicketStatusRequest', fields={
            'status': drf_serializers.CharField(required=False),
            'assignee': drf_serializers.CharField(required=False),
        }),
        responses={
            200: JiraTicketSerializer,
            400: _ErrorSerializer,
            404: _ErrorSerializer,
        },
    )
    def patch(self, request, issue_key):
        ticket = generics.get_object_or_404(JiraTicket, issue_key=issue_key)
        
        status = request.data.get('status')
        assignee = request.data.get('assignee')
        
        if status:
            ticket.status = status
        if assignee:
            ticket.assignee = assignee
        
        ticket.save()
        return Response(JiraTicketSerializer(ticket).data)


class CreateTicketView(APIView):
    """POST /api/tickets/create/ — create a new Jira ticket."""

    @extend_schema(
        tags=['Tickets'],
        summary='Create new ticket',
        description='Create a new Jira ticket with summary, description, assignee, etc.',
        request=inline_serializer('CreateTicketRequest', fields={
            'summary': drf_serializers.CharField(),
            'description': drf_serializers.CharField(required=False),
            'assignee': drf_serializers.CharField(required=False),
            'priority': drf_serializers.CharField(required=False),
            'issue_type': drf_serializers.CharField(required=False),
        }),
        responses={
            201: JiraTicketSerializer,
            400: _ErrorSerializer,
        },
    )
    def post(self, request):
        summary = request.data.get('summary', '').strip()
        description = request.data.get('description', '').strip()
        assignee = request.data.get('assignee', 'Unassigned').strip()
        priority = request.data.get('priority', 'Medium').strip()
        issue_type = request.data.get('issue_type', 'Task').strip()
        status = request.data.get('status', 'Active').strip() or 'Active'
        
        if not summary:
            return Response({'error': 'Summary is required.'}, status=400)
        
        # Generate issue key (e.g., TASK-1001, TASK-1002, etc.)
        from django.db.models import Max
        from django.utils import timezone
        last_ticket = JiraTicket.objects.filter(
            issue_key__startswith='TASK-'
        ).order_by('issue_key').last()
        
        if last_ticket:
            last_num = int(last_ticket.issue_key.split('-')[1])
            new_num = last_num + 1
        else:
            new_num = 1001
        
        issue_key = f'TASK-{new_num}'
        
        ticket = JiraTicket.objects.create(
            issue_key=issue_key,
            summary=summary,
            description=description,
            assignee=assignee,
            priority=priority,
            issue_type=issue_type,
            status=status,
            reporter='Extension User',
            created_date=timezone.now(),
            updated_date=timezone.now(),
        )
        
        return Response(JiraTicketSerializer(ticket).data, status=201)


class DeleteView(APIView):
    """
    DELETE /api/delete/<entity_type>/<id>/

    entity_type : commits | tickets | pages | meetings | projects
    id          : sha (commits), issue_key (tickets), uuid (everything else)
    """
    @extend_schema(
        tags=['Delete'],
        summary='Delete an entity',
        description=(
            'Remove a record from the knowledge base.\n\n'
            '**entity_type** must be one of: `commits`, `tickets`, `pages`, `meetings`, `projects`.\n\n'
            '**id** is the SHA for commits, issue_key for tickets, or UUID for everything else.'
        ),
        responses={
            200: _DeleteResponseSerializer,
            400: _ErrorSerializer,
            404: _ErrorSerializer,
        },
    )
    def delete(self, request, entity_type, id):
        if entity_type not in ENTITY_MAP:
            return Response(
                {'error': f'Unknown entity type "{entity_type}". '
                          f'Choose from: {", ".join(ENTITY_MAP.keys())}'},
                status=400,
            )
        model, lookup_field = ENTITY_MAP[entity_type]
        obj = generics.get_object_or_404(model, **{lookup_field: id})
        obj.delete()
        return Response({'deleted': True, 'entity_type': entity_type, 'id': id})
