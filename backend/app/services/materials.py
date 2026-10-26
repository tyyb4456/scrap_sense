"""Explicit material aliases shared by intake-facing price queries.

Matching is deliberate rather than fuzzy: a material only matches when its
normalized spelling is in the same explicit alias group. Substring matching is
not used because it would confuse different materials (for example "paper" and
"newspaper", or "iron" and "iron oxide").
"""

from __future__ import annotations

# Keys are canonical identifiers. Values are the only accepted spellings.
MATERIAL_ALIASES: dict[str, tuple[str, ...]] = {
    "plastic": (
        "plastic",
        "plastics",
        "pet",
        "pet bottle",
        "pet bottles",
        "plastic bottle",
        "plastic bottles",
        "polythene",
        "polyethylene",
        "hdpe",
        "ldpe",
        "pvc",
    ),
    "paper": (
        "paper",
        "kaghaz",
        "kagaz",
        "cardboard",
        "card board",
        "carton",
        "cartons",
        "paperboard",
        "newspaper",
    ),
    "iron": (
        "iron",
        "loha",
        "steel",
        "sariya",
        "sarya",
        "rebar",
        "ferrous",
        "scrap iron",
    ),
    "copper": (
        "copper",
        "tamba",
        "tambe",
        "copper wire",
    ),
    "aluminum": (
        "aluminum",
        "aluminium",
        "aluminum foil",
        "aluminium foil",
    ),
    "brass": (
        "brass",
        "peetal",
        "peetal scrap",
    ),
    "glass": (
        "glass",
        "sheesha",
    ),
    "textile": (
        "textile",
        "cloth",
        "kapra",
        "kapda",
        "fabric",
    ),
}

MATERIAL_LABELS: dict[str, str] = {
    "plastic": "Plastic",
    "paper": "Paper",
    "iron": "Iron",
    "copper": "Copper",
    "aluminum": "Aluminum",
    "brass": "Brass",
    "glass": "Glass",
    "textile": "Textile",
}


def normalize_text(value: str | None) -> str | None:
    """Collapse whitespace and case so stored and requested values compare."""
    if value is None:
        return None
    normalized = " ".join(value.strip().lower().split())
    return normalized or None


def normalize_material(value: str | None) -> str | None:
    """Return a canonical material identifier, or a normalized unknown value."""
    normalized = normalize_text(value)
    if normalized is None:
        return None
    for canonical, aliases in MATERIAL_ALIASES.items():
        if normalized == canonical or normalized in aliases:
            return canonical
    return normalized


def material_aliases(value: str | None) -> tuple[str, ...]:
    """Return all explicit query spellings for a material."""
    normalized = normalize_material(value)
    if normalized is None:
        return ()
    aliases = MATERIAL_ALIASES.get(normalized)
    if aliases is None:
        return (normalized,)
    return (normalized, *aliases)


def material_label(value: str | None) -> str:
    """Human-readable label without exposing an unknown spelling as canonical."""
    normalized = normalize_material(value)
    if normalized is None:
        return "Unknown material"
    return MATERIAL_LABELS.get(normalized, normalized.replace("-", " ").title())
