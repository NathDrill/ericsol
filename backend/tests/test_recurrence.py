from app.utils.recurrence import normalize_recurrence as n

def test_aliases():
    assert n("mensuel") == "monthly"
    assert n("Mensuelle") == "monthly"
    assert n("Trimestriel") == "quarterly"
    assert n("semestriel") == "semiannual"
    assert n("annuel") == "annual"
    assert n("yearly") == "annual"

def test_one_time():
    assert n("one_time") == "one_time"
    assert n("ponctuel") == "one_time"
    assert n("achat") == "one_time"

def test_defaults():
    assert n("") == "monthly"
    assert n(None) == "monthly"
    assert n("valeur inconnue") == "monthly"
