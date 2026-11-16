from django.db import migrations


FREE_ENTITLEMENTS = {
    "catalog_discovery": True,
    "catalog_search": True,
    "free_resources": True,
    "basic_activities": True,
    "personal_dashboard": True,
    "basic_progress": True,
    "selected_learning_paths": True,
    # AI tutoring is not implemented in this source copy.
    "ai_tutor_requests_per_day": 0,
}


def seed_plans(apps, schema_editor):
    Plan = apps.get_model("learning", "LearningSubscriptionPlan")
    Plan.objects.update_or_create(
        code="free",
        defaults={
            "name": "Free",
            "tier": "free",
            "description": "Free access to selected published learning resources and basic progress features.",
            "amount": None,
            "currency": "",
            "billing_interval": "none",
            "entitlements": FREE_ENTITLEMENTS,
            "is_active": True,
        },
    )
    Plan.objects.update_or_create(
        code="premium",
        defaults={
            "name": "Premium",
            "tier": "premium",
            "description": "Expanded learning access; price, billing interval, and premium entitlements require separate approval.",
            "amount": None,
            "currency": "",
            "billing_interval": "none",
            "entitlements": {},
            "is_active": False,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0006_individual_subscription_access_tiers"),
    ]

    operations = [
        migrations.RunPython(seed_plans, migrations.RunPython.noop),
    ]
