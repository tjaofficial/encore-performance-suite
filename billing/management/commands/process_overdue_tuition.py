from datetime import date
from django.core.management.base import BaseCommand, CommandError
from billing.overdue_services import process_overdue

class Command(BaseCommand):
    help = "Preview or send overdue tuition milestones. Dry-run is the default."
    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",help="Send notices and create review flags")
        parser.add_argument("--studio-id",type=int)
        parser.add_argument("--date",help="YYYY-MM-DD (testing)")
    def handle(self,*args,**options):
        try: as_of=date.fromisoformat(options["date"]) if options["date"] else None
        except ValueError as exc: raise CommandError("Invalid --date") from exc
        outcome=process_overdue(as_of=as_of,dry_run=not options["apply"],studio_id=options["studio_id"])
        self.stdout.write(str(outcome))
        if not options["apply"]:self.stdout.write("DRY RUN. No email, notifications, or database changes.")
