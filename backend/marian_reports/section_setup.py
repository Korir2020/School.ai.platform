"""Which report sections a school shows. Visibility only: no grading rules."""
from __future__ import annotations

from .config import ReportConfig
from .frameworks import STAGE_PRESETS

# Off unless a school switches them on. Every other known section defaults to on.
OFF_BY_DEFAULT = {"trend_insights"}


class SectionError(ValueError):
    pass


def allowed_keys() -> set:
    keys = set(ReportConfig().sections) | {"trend_insights"}
    for preset in STAGE_PRESETS.values():
        keys |= set(preset.get("sections", {}))
    return keys


def effective_sections(cfg) -> dict:
    return {k: bool(cfg.sections.get(k, k not in OFF_BY_DEFAULT))
            for k in sorted(allowed_keys())}


def apply_sections(cfg, body) -> dict:
    """Validate everything first, then apply. Returns {name: [old, new]} for real changes."""
    if (not isinstance(body, dict) or not isinstance(body.get("sections"), dict)
            or not body["sections"]):
        raise SectionError('Send {"sections": {"<name>": true or false}}.')
    new = body["sections"]
    unknown = sorted(set(new) - allowed_keys())
    if unknown:
        raise SectionError("Unknown section(s): " + ", ".join(unknown))
    bad = sorted(k for k, v in new.items() if not isinstance(v, bool))
    if bad:
        raise SectionError("Values must be true or false: " + ", ".join(bad))
    before = effective_sections(cfg)
    changed = {k: [before[k], v] for k, v in new.items() if before[k] != v}
    for k, (_, v) in changed.items():
        cfg.sections[k] = v
    return changed
