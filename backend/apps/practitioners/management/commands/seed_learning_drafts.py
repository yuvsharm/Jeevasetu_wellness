from django.core.management.base import BaseCommand
from apps.appointments.models import TherapyOption
from apps.practitioners.models import TherapyLearningGuide
class Command(BaseCommand):
    help = "Create unpublished empty guides for active therapies without replacing existing content."
    def handle(self, *args, **options):
        created = 0
        for therapy in TherapyOption.objects.filter(is_active=True):
            _, new = TherapyLearningGuide.objects.get_or_create(therapy=therapy, defaults={"title_en": therapy.name})
            created += int(new)
        self.stdout.write(f"Created {created} unpublished drafts. Existing content preserved.")
