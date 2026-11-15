from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from schools.models import School

from .models import BillingProfile


@receiver(post_save, sender=School, dispatch_uid="billing.create_new_school_trial")
def create_new_school_trial(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        BillingProfile.objects.get_or_create(
            school=instance,
            defaults={
                "access_type": "trial",
                "status": "trial_active",
                "trial_started_at": timezone.now(),
            },
        )
