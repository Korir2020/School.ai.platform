"""Per-school report options.

Validated here, stored in ReportSettings.options, applied to ReportConfig.
Defaults keep today's behaviour: nothing changes until an admin saves a value.
"""

OPTION_CHOICES = {
    "previous_exams": [1, 2, 3],
    "rank_by": ["best_points", "total_marks"],
    "tie_policy": ["competition", "dense", "ordinal"],
}
KEYS = ("previous_exams", "rank_by", "tie_policy", "allow_provisional",
        "weak_pct", "footer_note")
MAX_FOOTER = 200


class OptionError(ValueError):
    pass


def validate_options(body):
    """Return the cleaned values. A footer of '' becomes None (reset to default)."""
    if not isinstance(body, dict):
        raise OptionError('Send {"options": {"<name>": value}}.')
    unknown = sorted(set(body) - set(KEYS))
    if unknown:
        raise OptionError("Unknown option(s): " + ", ".join(unknown))
    out = {}
    for k, v in body.items():
        if k == "previous_exams":
            if type(v) is not int or v not in OPTION_CHOICES[k]:
                raise OptionError("previous_exams must be 1, 2 or 3.")
        elif k in ("rank_by", "tie_policy"):
            if not isinstance(v, str) or v not in OPTION_CHOICES[k]:
                raise OptionError(k + " must be one of: " + ", ".join(OPTION_CHOICES[k]))
        elif k == "allow_provisional":
            if type(v) is not bool:
                raise OptionError("allow_provisional must be true or false.")
        elif k == "weak_pct":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100:
                raise OptionError("weak_pct must be a number from 0 to 100.")
        elif k == "footer_note":
            if not isinstance(v, str) or len(v.strip()) > MAX_FOOTER:
                raise OptionError("footer_note must be text of at most 200 characters.")
            v = v.strip() or None
        out[k] = v
    return out


def apply_options(cfg, saved):
    if not isinstance(saved, dict):
        return
    n = saved.get("previous_exams")
    if type(n) is int and n in OPTION_CHOICES["previous_exams"]:
        cfg.history_limit = n + 1            # the limit counts the current exam too
    if saved.get("rank_by") in OPTION_CHOICES["rank_by"]:
        cfg.rank_by = saved["rank_by"]
        if cfg.rank_by == "total_marks":
            cfg.rank_note = "Position ranked by total marks"
    if saved.get("tie_policy") in OPTION_CHOICES["tie_policy"]:
        cfg.tie_policy = saved["tie_policy"]
    if type(saved.get("allow_provisional")) is bool:
        cfg.allow_provisional = saved["allow_provisional"]
    w = saved.get("weak_pct")
    if isinstance(w, (int, float)) and not isinstance(w, bool) and 0 <= w <= 100:
        cfg.weak_pct = float(w)
    f = saved.get("footer_note")
    if isinstance(f, str) and f.strip():
        cfg.footer_note = f.strip()


def effective_options(cfg):
    return {
        "previous_exams": max(1, min(3, cfg.history_limit - 1)),
        "rank_by": cfg.rank_by,
        "tie_policy": cfg.tie_policy,
        "allow_provisional": cfg.allow_provisional,
        "weak_pct": cfg.weak_pct,
        "footer_note": cfg.footer_note,
    }
