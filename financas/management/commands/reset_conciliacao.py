"""
Management command to reset stuck conciliation jobs.

Usage:
    python manage.py reset_conciliacao                  # Reset all stuck 'running' jobs
    python manage.py reset_conciliacao --group "LANA"   # Reset jobs for a specific group
    python manage.py reset_conciliacao --job-id 1       # Reset a specific job by ID
    python manage.py reset_conciliacao --list           # List all conciliation jobs
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from financas.models import ConciliacaoJob


class Command(BaseCommand):
    help = 'Reset stuck conciliation jobs or list job status'

    def add_arguments(self, parser):
        parser.add_argument(
            '--group',
            type=str,
            help='Filter by group name (partial match)',
        )
        parser.add_argument(
            '--job-id',
            type=int,
            help='Reset a specific job by ID',
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List all conciliation jobs without resetting',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Reset ALL running jobs (use with caution)',
        )

    def handle(self, *args, **options):
        if options['list']:
            self._list_jobs(options.get('group'))
            return

        if options['job_id']:
            self._reset_job_by_id(options['job_id'])
            return

        if options['all'] or options['group']:
            self._reset_running_jobs(options.get('group'), options.get('all'))
            return

        # Default: show help
        self.stdout.write(self.style.WARNING(
            'No action specified. Use --list, --job-id, --group, or --all.\n'
            'Run "python manage.py reset_conciliacao --help" for more info.'
        ))

    def _list_jobs(self, group_filter=None):
        """List all conciliation jobs."""
        qs = ConciliacaoJob.objects.select_related('group').order_by('-started_at')
        
        if group_filter:
            qs = qs.filter(group__name__icontains=group_filter)

        if not qs.exists():
            self.stdout.write(self.style.WARNING('No conciliation jobs found.'))
            return

        self.stdout.write(self.style.SUCCESS(f'\n{"ID":<6} {"Group":<30} {"Status":<12} {"Started":<20} {"Progress":<10}'))
        self.stdout.write('-' * 90)

        for job in qs[:50]:  # Limit to 50 most recent
            group_name = job.group.name if job.group else 'N/A'
            started = job.started_at.strftime('%Y-%m-%d %H:%M:%S') if job.started_at else 'N/A'
            progress = f"{job.processed_count}/{job.total_guias}"
            
            # Color based on status
            if job.status == 'running':
                status_display = self.style.WARNING(job.status.ljust(12))
            elif job.status == 'completed':
                status_display = self.style.SUCCESS(job.status.ljust(12))
            elif job.status == 'failed':
                status_display = self.style.ERROR(job.status.ljust(12))
            else:
                status_display = job.status.ljust(12)

            self.stdout.write(f'{job.id:<6} {group_name[:30]:<30} {status_display} {started:<20} {progress:<10}')

        self.stdout.write('')

    def _reset_job_by_id(self, job_id):
        """Reset a specific job by ID."""
        try:
            job = ConciliacaoJob.objects.select_related('group').get(id=job_id)
        except ConciliacaoJob.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Job with ID {job_id} not found.'))
            return

        group_name = job.group.name if job.group else 'N/A'
        self.stdout.write(f'Found job {job_id} for group "{group_name}" with status "{job.status}"')

        if job.status not in ['running', 'pending']:
            self.stdout.write(self.style.WARNING(
                f'Job is already {job.status}. No action needed.'
            ))
            return

        job.status = 'failed'
        job.error_message = 'Manually reset via management command'
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'completed_at'])

        self.stdout.write(self.style.SUCCESS(f'✓ Job {job_id} has been reset to "failed".'))

    def _reset_running_jobs(self, group_filter=None, reset_all=False):
        """Reset all running jobs, optionally filtered by group."""
        qs = ConciliacaoJob.objects.filter(status='running')
        
        if group_filter:
            qs = qs.filter(group__name__icontains=group_filter)
        elif not reset_all:
            self.stdout.write(self.style.ERROR(
                'You must specify --group or --all to reset running jobs.'
            ))
            return

        jobs = list(qs.select_related('group'))
        
        if not jobs:
            self.stdout.write(self.style.WARNING('No running jobs found to reset.'))
            return

        self.stdout.write(f'Found {len(jobs)} running job(s) to reset:')
        for job in jobs:
            group_name = job.group.name if job.group else 'N/A'
            self.stdout.write(f'  - Job {job.id}: {group_name}')

        # Confirm
        if not reset_all:
            confirm = input('\nReset these jobs? [y/N]: ').strip().lower()
            if confirm != 'y':
                self.stdout.write(self.style.WARNING('Aborted.'))
                return

        # Reset all
        count = qs.update(
            status='failed',
            error_message='Manually reset via management command',
            completed_at=timezone.now()
        )

        self.stdout.write(self.style.SUCCESS(f'✓ Reset {count} job(s) to "failed".'))
