from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from billing.models import BillingProfile, BillingSubscription, PerpetualLicence


class Command(BaseCommand):
    help = "Mark elapsed Marian cloud subscriptions and service periods as expired."

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        subs = BillingSubscription.objects.filter(status="active", ends_at__lte=now)
        subscription_count = subs.count()
        subs.update(status="expired")

        expired_school_ids = list(BillingSubscription.objects.filter(
            status="expired", school__billing_profile__status="subscription_active",
        ).values_list("school_id", flat=True).distinct())
        for school_id in expired_school_ids:
            if not BillingSubscription.objects.filter(
                school_id=school_id, status="active", ends_at__gt=now,
            ).exists():
                BillingProfile.objects.filter(
                    school_id=school_id, status="subscription_active",
                ).update(status="subscription_expired")

        expired_cloud = PerpetualLicence.objects.filter(
            status="active", deployment_type="cloud", service_until__lte=now,
            school__billing_profile__status="licence_active",
        )
        cloud_school_ids = list(expired_cloud.values_list("school_id", flat=True).distinct())
        for school_id in cloud_school_ids:
            BillingProfile.objects.filter(
                school_id=school_id, status="licence_active",
            ).update(status="service_expired")

        self.stdout.write(self.style.SUCCESS(
            f"Expired {subscription_count} subscription(s); updated {len(expired_school_ids)} subscription profile(s) and {len(cloud_school_ids)} cloud-service profile(s)."
        ))
