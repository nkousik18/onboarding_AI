from django.urls import path
from . import views

urlpatterns = [
    # Chat
    path("chat/", views.ChatView.as_view(), name="chat"),
    path("query/", views.QueryView.as_view(), name="query"),  # Alias for chat
    # Commits
    path("commits/", views.CommitListView.as_view(), name="commit-list"),
    path("commits/<str:sha>/", views.CommitDetailView.as_view(), name="commit-detail"),
    # Tickets
    path("tickets/", views.TicketListView.as_view(), name="ticket-list"),
    path("tickets/create/", views.CreateTicketView.as_view(), name="ticket-create"),
    path(
        "tickets/<str:issue_key>/",
        views.TicketDetailView.as_view(),
        name="ticket-detail",
    ),
    path(
        "tickets/<str:issue_key>/status/",
        views.UpdateTicketStatusView.as_view(),
        name="ticket-status",
    ),
    path(
        "tickets/<str:issue_key>/context/",
        views.TicketContextView.as_view(),
        name="ticket-context",
    ),
    path(
        "tickets/<str:issue_key>/comments/",
        views.TicketCommentsView.as_view(),
        name="ticket-comments",
    ),
    # Confluence Pages
    path("pages/", views.PageListView.as_view(), name="page-list"),
    path("pages/<uuid:pk>/", views.PageDetailView.as_view(), name="page-detail"),
    # Meetings
    path("meetings/", views.MeetingListView.as_view(), name="meeting-list"),
    path(
        "meetings/<uuid:pk>/", views.MeetingDetailView.as_view(), name="meeting-detail"
    ),
    # Teams
    path("teams/messages/", views.TeamsMessagesView.as_view(), name="teams-messages"),
    # Activity
    path("activity/", views.ActivityView.as_view(), name="activity"),
    # Projects
    path("projects/", views.ProjectListView.as_view(), name="project-list"),
    path(
        "projects/<uuid:pk>/", views.ProjectDetailView.as_view(), name="project-detail"
    ),
    path(
        "projects/<uuid:pk>/add-member/", views.ProjectAddMemberView.as_view(), name="project-add-member"
    ),
    # Register
    path("register/", views.RegisterView.as_view(), name="register"),
    # Employees
    path("employees/", views.EmployeeListView.as_view(), name="employee-list"),
    path("employees/<uuid:pk>/", views.EmployeeDetailView.as_view(), name="employee-detail"),
    # Sprints
    path("sprints/", views.SprintListView.as_view(), name="sprint-list"),
    path("sprints/<int:sprint_number>/", views.SprintDetailView.as_view(), name="sprint-detail"),
    path("sprints/<int:sprint_number>/tickets/", views.SprintTicketsOutcomeView.as_view(), name="sprint-tickets-outcome"),
    path("sprints/<int:sprint_number>/meetings/", views.SprintMeetingsView.as_view(), name="sprint-meetings"),
    # Decisions
    path("decisions/", views.DecisionListView.as_view(), name="decision-list"),
    path("decisions/<uuid:pk>/", views.DecisionDetailView.as_view(), name="decision-detail"),
    # Search
    path("search/", views.SearchView.as_view(), name="search"),
    # test
    path("test/", views.HelloPreetyView.as_view(), name="search"),
    # Ingest
    path("ingest/github/", views.IngestGithubView.as_view(), name="ingest-github"),
    path("ingest/jira/", views.IngestJiraView.as_view(), name="ingest-jira"),
    path("ingest/confluence/", views.IngestConfluenceView.as_view(), name="ingest-confluence"),
    path("ingest/meetings/", views.IngestMeetingView.as_view(), name="ingest-meetings"),
    # Delete
    path("delete/<str:entity_type>/<str:id>/", views.DeleteView.as_view(), name="delete"),
]
