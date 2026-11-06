from django.db.models import F


def registered_marks(queryset, academic_year):
    """Restrict performance rows to the subject set registered by each learner."""
    year_id = getattr(academic_year, "pk", academic_year)
    return queryset.filter(
        subject__registrations__academic_year_id=year_id,
        subject__registrations__student_id=F("student_id"),
    ).distinct()
