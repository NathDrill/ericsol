from app.api.routes.contracts import _clean_vendor_name as c

def test_legal_forms_hidden():
    for v in ["SAS", "SA", "société anonyme", "société à responsabilité limitée à associé unique", "SARL"]:
        assert c(v) is None, v

def test_infoclip_hidden():
    assert c("Infoclip") is None

def test_real_names_kept():
    assert c("Orange Business") == "Orange Business"
    assert c("GTT") == "GTT"
    assert c("Intuity SAS") == "Intuity SAS"
    assert c("BMW Finance, Société en Nom Collectif au capital de 87.000.000 Euros") == "BMW Finance"

def test_empty():
    assert c("") is None
    assert c(None) is None
