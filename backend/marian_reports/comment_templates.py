"""Neutral, editable comment defaults tied to a school's saved result scale.

Templates may use only the supplied placeholders. Defaults describe recorded
school results and possible next steps; they do not claim personal observations.
"""
from string import Formatter

FIELDS = ("subject", "class_teacher", "principal")
MAX_TEMPLATE_LENGTH = 400
ALLOWED_PLACEHOLDERS = {"level", "subject", "scale", "levels", "stage"}


def stage_for_scale(min_level, max_level):
    if max_level <= 6:
        return "Primary"
    if min_level >= 7 and max_level <= 9:
        return "Junior"
    if min_level >= 10 and max_level <= 12:
        return "Senior"
    return "CBC"


def default_templates(labels, *, kind="numeric", scale_name="school scale", stage=""):
    """Build neutral defaults for each label in the school's own scale."""
    out = {}
    for key, label in labels:
        label = str(label)
        if kind == "level":
            out[str(key)] = {
                "subject": (
                    "For {subject}, use the recorded {level} descriptor and available work "
                    "to plan a suitable next learning step."
                ),
            }
        else:
            out[str(key)] = {
                "subject": (
                    "The recorded result is {level} on the {scale} for {subject}. "
                    "Use the recorded work to plan the next learning step."
                ),
                "class_teacher": (
                    "The current overall result is {level} on the {scale}. Review the "
                    "recorded progress with the learner and agree on a practical next step."
                ),
                "principal": (
                    "The school's current assessment records {level} on the {scale}. "
                    "Review progress and support the agreed learning priorities."
                ),
            }
    if kind == "level":
        labels_text = ", ".join(str(label) for _key, label in labels) or "the recorded school-defined levels"
        out["__overall__"] = {
            "class_teacher": (
                "Recorded {stage} descriptors include {levels}. Review the subject feedback "
                "with the learner and agree on a practical next learning step."
            ),
            "principal": (
                "This internal {stage} report records these school-defined descriptors: {levels}. "
                "Review the evidence and support the agreed learning priorities."
            ),
        }
        # The values are only safe defaults. Runtime rendering substitutes the
        # learner's actually recorded labels instead of this scale-wide list.
        _ = labels_text
    return out


def merge_templates(defaults, saved):
    """Overlay saved school wording on current scale defaults without losing new levels."""
    saved = saved if isinstance(saved, dict) else {}
    out = {key: dict(fields) for key, fields in defaults.items()}
    for key, fields in saved.items():
        if key not in out or not isinstance(fields, dict):
            continue
        for field, text in fields.items():
            if field in out[key] and isinstance(text, str) and text.strip():
                out[key][field] = text.strip()
    return out


def clean_templates(defaults, body):
    """Validate a partial editable override; omitted/blank fields use safe defaults."""
    if not isinstance(body, dict):
        raise ValueError("templates must be an object keyed by school scale label.")
    unknown = sorted(set(body) - set(defaults))
    if unknown:
        raise ValueError("Unknown scale entry: " + ", ".join(unknown[:5]))
    cleaned = {}
    for key, fields in body.items():
        if not isinstance(fields, dict):
            raise ValueError("Each scale entry must contain comment fields.")
        unknown_fields = sorted(set(fields) - set(defaults[key]))
        if unknown_fields:
            raise ValueError("Unsupported comment field: " + ", ".join(unknown_fields))
        row = {}
        for field, value in fields.items():
            if not isinstance(value, str):
                raise ValueError("Comment templates must be text.")
            value = " ".join(value.split())
            if not value:
                row[field] = ""
                continue
            if len(value) > MAX_TEMPLATE_LENGTH:
                raise ValueError(f"Comment templates must be at most {MAX_TEMPLATE_LENGTH} characters.")
            try:
                placeholders = {name for _literal, name, _spec, _conversion in Formatter().parse(value) if name}
            except ValueError:
                raise ValueError("Template braces are not valid.")
            if placeholders - ALLOWED_PLACEHOLDERS:
                raise ValueError("Unsupported placeholder(s): " + ", ".join(sorted(placeholders - ALLOWED_PLACEHOLDERS)))
            row[field] = value
        if row:
            cleaned[key] = row
    return cleaned


def render_template(template, *, level="", subject="", scale="school scale", levels="", stage="CBC"):
    if not isinstance(template, str):
        return ""
    values = {"level": str(level), "subject": str(subject), "scale": str(scale),
              "levels": str(levels), "stage": str(stage)}
    try:
        return template.format_map(values)
    except (KeyError, ValueError, IndexError):
        return template


def numeric_templates(scheme, saved=None):
    labels = [(band.label, band.label) for band in sorted(scheme.bands, key=lambda row: row.min_pct, reverse=True)]
    defaults = default_templates(labels, kind="numeric", scale_name="school grading scale")
    return merge_templates(defaults, saved)


def level_templates(scale, saved=None):
    stage = stage_for_scale(scale.min_level, scale.max_level)
    labels = [(item.get("key", ""), item.get("label", item.get("key", "")))
              for item in (scale.levels if isinstance(scale.levels, list) else [])
              if isinstance(item, dict) and item.get("key")]
    defaults = default_templates(labels, kind="level", scale_name="school-defined achievement scale",
                                 stage=stage)
    return merge_templates(defaults, saved)
