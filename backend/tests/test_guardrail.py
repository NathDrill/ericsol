from types import SimpleNamespace
from app.api.routes.contracts import _amount_guardrail

def _contract(title, mrr, rec="monthly"):
    return SimpleNamespace(title=title, amount_mrr=mrr, amount_arr=mrr*12, recurrence=rec)

def test_vehicle_purchase_is_one_time():
    c = _contract("Convention de commande d'un véhicule motorisé", 34733.46)
    r = _amount_guardrail(c, {"contract_label": c.title}, "")
    assert r and r.get("guardrail") == "achat_ponctuel"
    assert c.recurrence == "one_time"
    assert c.amount_mrr == 0.0
    assert c.amount_arr == 34733.46

def test_lease_stays_recurring():
    c = _contract("Location avec Option d'Achat (LOA Select) 48 mois", 16968.0)
    r = _amount_guardrail(c, {"contract_label": c.title}, "")
    assert c.recurrence == "monthly"  # LOA = leasing, pas achat unique

def test_colocation_not_one_time():
    c = _contract("Colocation et interconnexions datacenter Paris (PA5, PA6, PA7)", 36145.86)
    _amount_guardrail(c, {"contract_label": c.title}, "")
    assert c.recurrence == "monthly"

def test_small_monthly_no_flag():
    c = _contract("Renouvellement service IP Transit 700 Mbps", 850.0)
    r = _amount_guardrail(c, {"contract_label": c.title}, "")
    assert r is None
