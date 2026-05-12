"""
Management command to populate Project 2 and update sprint timelines
"""
import uuid
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from knowledge_base.models import Project, Sprint, JiraTicket, SprintTicket


class Command(BaseCommand):
    help = 'Populate Project 2 and update sprint timelines to May'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting data population...'))
        
        # ── Step 1: Update Employee Onboarding Portal sprints to May ────
        self.update_employee_onboarding_sprints()
        
        # ── Step 2: Create Project 2 ────────────────────────────────────
        project2 = self.create_project2()
        
        # ── Step 3: Create sprints for Project 2 ────────────────────────
        self.create_project2_sprints(project2)
        
        # ── Step 4: Create tickets for Project 2 ────────────────────────
        self.create_project2_tasks(project2)
        
        self.stdout.write(self.style.SUCCESS('✓ Data population completed successfully!'))

    def update_employee_onboarding_sprints(self):
        """Update Employee Onboarding Portal sprints to May 2026"""
        self.stdout.write('Updating Employee Onboarding Portal sprints to May...')
        
        employee_proj = Project.objects.filter(name='Employee Onboarding Portal').first()
        if not employee_proj:
            self.stdout.write(self.style.WARNING('Employee Onboarding Portal not found'))
            return
        
        # May 2026 dates
        may_start = datetime(2026, 5, 1).date()
        
        sprints = employee_proj.sprints.all().order_by('sprint_number')
        for i, sprint in enumerate(sprints):
            # Sprint 1: May 1-15 (Past/Completed)
            # Sprint 2: May 16-30 (Current/Ongoing)
            # Sprint 3: June 1-15 (Future)
            
            if i == 0:
                sprint.start_date = datetime(2026, 4, 1).date()
                sprint.end_date = may_start - timedelta(days=1)
                sprint.status = 'completed'
                sprint.name = 'Sprint 1 - Infrastructure'
            elif i == 1:
                sprint.start_date = may_start
                sprint.end_date = datetime(2026, 5, 15).date()
                sprint.status = 'current'
                sprint.name = 'Sprint 2 - Core Features'
            else:
                sprint.start_date = datetime(2026, 5, 16).date()
                sprint.end_date = datetime(2026, 5, 30).date()
                sprint.status = 'planned'
                sprint.name = 'Sprint 3 - Integration'
            
            sprint.save()
            self.stdout.write(f'  ✓ Updated {sprint.name}')

    def create_project2(self):
        """Create Project 2 - Payment Processing System"""
        self.stdout.write('Creating Project 2...')
        
        # Check if already exists
        existing = Project.objects.filter(name='Payment Processing System').first()
        if existing:
            self.stdout.write('  Project 2 already exists')
            return existing
        
        project2 = Project.objects.create(
            id=uuid.uuid4(),
            name='Payment Processing System',
            description='Secure payment gateway and transaction management system',
            status='active',
            epic_key='PAY-100',
            jira_project_key='PAY',
            owner='Finance Team',
            team_members='John Doe, Sarah Smith, Mike Johnson',
            tags=['payment', 'backend', 'critical']
        )
        
        self.stdout.write(f'  ✓ Created {project2.name} (ID: {project2.id})')
        return project2

    def create_project2_sprints(self, project2):
        """Create 3 sprints for Project 2"""
        self.stdout.write('Creating Project 2 sprints...')
        
        sprints_data = [
            {
                'sprint_number': 1,
                'name': 'Sprint 1 - Payment Gateway Setup',
                'start_date': datetime(2026, 4, 1).date(),
                'end_date': datetime(2026, 4, 30).date(),
                'status': 'completed',
                'goal': 'Set up core payment gateway infrastructure',
            },
            {
                'sprint_number': 2,
                'name': 'Sprint 2 - Transaction Processing',
                'start_date': datetime(2026, 5, 1).date(),
                'end_date': datetime(2026, 5, 15).date(),
                'status': 'current',
                'goal': 'Implement secure transaction processing logic',
            },
            {
                'sprint_number': 3,
                'name': 'Sprint 3 - Reporting & Analytics',
                'start_date': datetime(2026, 5, 16).date(),
                'end_date': datetime(2026, 5, 30).date(),
                'status': 'planned',
                'goal': 'Build reporting and analytics dashboard',
            },
        ]
        
        for data in sprints_data:
            sprint, created = Sprint.objects.get_or_create(
                sprint_number=data['sprint_number'],
                project=project2,
                defaults={
                    'id': uuid.uuid4(),
                    'name': data['name'],
                    'start_date': data['start_date'],
                    'end_date': data['end_date'],
                    'status': data['status'],
                    'goal': data['goal'],
                }
            )
            if created:
                self.stdout.write(f'  ✓ Created {sprint.name}')
            else:
                self.stdout.write(f'  - {sprint.name} already exists')

    def create_project2_tasks(self, project2):
        """Create dummy tasks for Project 2"""
        self.stdout.write('Creating Project 2 tasks...')
        
        tasks_data = [
            # Sprint 1 tasks (Completed)
            {
                'issue_key': 'PAY-101',
                'summary': 'Set up payment gateway API',
                'description': 'Integrate Stripe/PayPal API',
                'issue_type': 'Task',
                'status': 'Done',
                'priority': 'High',
                'assignee': 'John Doe',
                'sprint_number': 1,
            },
            {
                'issue_key': 'PAY-102',
                'summary': 'Configure SSL/TLS certificates',
                'description': 'Ensure secure HTTPS connection',
                'issue_type': 'Task',
                'status': 'Done',
                'priority': 'Critical',
                'assignee': 'Sarah Smith',
                'sprint_number': 1,
            },
            {
                'issue_key': 'PAY-103',
                'summary': 'Database schema for transactions',
                'description': 'Design transaction storage schema',
                'issue_type': 'Task',
                'status': 'Done',
                'priority': 'High',
                'assignee': 'Mike Johnson',
                'sprint_number': 1,
            },
            # Sprint 2 tasks (Ongoing)
            {
                'issue_key': 'PAY-201',
                'summary': 'Implement payment processing logic',
                'description': 'Core transaction processing engine',
                'issue_type': 'Task',
                'status': 'In Progress',
                'priority': 'Critical',
                'assignee': 'John Doe',
                'sprint_number': 2,
            },
            {
                'issue_key': 'PAY-202',
                'summary': 'Add error handling and retries',
                'description': 'Handle failed transactions gracefully',
                'issue_type': 'Task',
                'status': 'In Progress',
                'priority': 'High',
                'assignee': 'Sarah Smith',
                'sprint_number': 2,
            },
            {
                'issue_key': 'PAY-203',
                'summary': 'Webhook implementation',
                'description': 'Handle payment notifications',
                'issue_type': 'Task',
                'status': 'To Do',
                'priority': 'Medium',
                'assignee': 'Mike Johnson',
                'sprint_number': 2,
            },
            {
                'issue_key': 'PAY-204',
                'summary': 'Payment logging system',
                'description': 'Comprehensive audit logging',
                'issue_type': 'Task',
                'status': 'To Do',
                'priority': 'Medium',
                'assignee': 'John Doe',
                'sprint_number': 2,
            },
            # Sprint 3 tasks (Future)
            {
                'issue_key': 'PAY-301',
                'summary': 'Build transaction dashboard',
                'description': 'Real-time transaction monitoring',
                'issue_type': 'Task',
                'status': 'To Do',
                'priority': 'High',
                'assignee': 'Sarah Smith',
                'sprint_number': 3,
            },
            {
                'issue_key': 'PAY-302',
                'summary': 'Create analytics reports',
                'description': 'Payment analytics and metrics',
                'issue_type': 'Task',
                'status': 'To Do',
                'priority': 'Medium',
                'assignee': 'Mike Johnson',
                'sprint_number': 3,
            },
            {
                'issue_key': 'PAY-303',
                'summary': 'User payment history page',
                'description': 'Display past transactions for users',
                'issue_type': 'Task',
                'status': 'To Do',
                'priority': 'Medium',
                'assignee': 'John Doe',
                'sprint_number': 3,
            },
        ]
        
        for data in tasks_data:
            ticket, created = JiraTicket.objects.get_or_create(
                issue_key=data['issue_key'],
                defaults={
                    'id': uuid.uuid4(),
                    'summary': data['summary'],
                    'description': data['description'],
                    'issue_type': data['issue_type'],
                    'status': data['status'],
                    'priority': data['priority'],
                    'assignee': data['assignee'],
                }
            )
            
            if created:
                # Link to sprint
                sprint = project2.sprints.filter(sprint_number=data['sprint_number']).first()
                if sprint:
                    SprintTicket.objects.get_or_create(
                        sprint=sprint,
                        ticket=ticket,
                        defaults={'added_date': sprint.start_date}
                    )
                self.stdout.write(f'  ✓ Created {data["issue_key"]}: {data["summary"]}')
            else:
                self.stdout.write(f'  - {data["issue_key"]} already exists')
