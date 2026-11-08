"""CBC Senior pathway and catalogue validation helpers.

Pathway subject tags describe eligibility only. This module deliberately does
not invent national subject counts, compulsory combinations, or grading rules.
"""


def is_cbc_senior(class_level):
    curriculum = getattr(class_level, "curriculum", None)
    return bool(
        curriculum and str(curriculum.code).upper() == "CBC"
        and 10 <= int(class_level.level_number) <= 12
    )


def pathway_matches_class(pathway, class_level):
    """A pathway is valid only for its CBC curriculum and applicable grade."""
    if pathway is None or not is_cbc_senior(class_level):
        return False
    if not pathway.is_active or pathway.curriculum_id != class_level.curriculum_id:
        return False
    cache = getattr(pathway, "_prefetched_objects_cache", {})
    if "class_levels" in cache:
        return any(row.pk == class_level.pk for row in cache["class_levels"])
    return pathway.class_levels.filter(pk=class_level.pk).exists()


def subject_definition_problem(definition, class_level, pathway):
    """Return a user-safe incompatibility reason, or an empty string.

    Definitions with no pathway tags are common learning areas; definitions
    with one or more tags are only available to the selected pathway(s).
    School-created subjects with no catalogue definition remain allowed.
    """
    if definition is None:
        return ""
    if definition.curriculum_id != class_level.curriculum_id:
        return "This subject belongs to a different curriculum."
    levels = list(definition.class_levels.all())
    if levels and class_level.pk not in {row.pk for row in levels}:
        return f"{definition.name} is not available for {class_level.name}."
    pathways = list(definition.pathways.all())
    if pathways and (pathway is None or pathway.pk not in {row.pk for row in pathways}):
        return f"{definition.name} is not available for the selected Senior pathway."
    return ""
