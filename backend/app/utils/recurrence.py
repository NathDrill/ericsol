"""Normalisation unique de la récurrence d'un contrat (source de vérité). Aucune dépendance interne."""

_ALIASES = {
    "monthly": "monthly", "mensuel": "monthly", "mensuelle": "monthly", "month": "monthly",
    "quarterly": "quarterly", "trimestriel": "quarterly", "trimestrielle": "quarterly", "quarter": "quarterly",
    "semiannual": "semiannual", "semi-annual": "semiannual", "semestriel": "semiannual",
    "semestrielle": "semiannual", "semiannuel": "semiannual", "semiannuelle": "semiannual",
    "annual": "annual", "annuel": "annual", "annuelle": "annual", "yearly": "annual", "year": "annual",
    "biannual": "biannual", "biennal": "biannual", "biennale": "biannual",
    "one_time": "one_time", "one-time": "one_time", "ponctuel": "one_time", "achat": "one_time",
}


def normalize_recurrence(value: str | None) -> str:
    """Renvoie une valeur de récurrence canonique. Défaut prudent : 'monthly'."""
    raw = (value or "").strip().lower()
    return _ALIASES.get(raw, "monthly")
