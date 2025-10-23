from django.core.management.base import BaseCommand
from django_rq import get_scheduler
from mailer.models import Campaign
from jobs.tasks import kickoff_campaign

class Command(BaseCommand):
    help = "Apply rq-scheduler cron schedules for enabled campaigns"

    def handle(self, *args, **options):
        scheduler = get_scheduler("default")
        # Clear existing jobs for kickoff to avoid duplicates
        for job in scheduler.get_jobs():
            if job.func_name.endswith("kickoff_campaign"):
                scheduler.cancel(job)
        for c in Campaign.objects.filter(enabled=True):
            scheduler.cron(c.schedule_cron, func=kickoff_campaign, args=[c.id], repeat=None, queue_name="default")
            self.stdout.write(self.style.SUCCESS(f"Scheduled campaign {c.id} with cron '{c.schedule_cron}'"))
