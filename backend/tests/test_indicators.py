from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.contract import Contract
from app.services.contract_service import indicators

def _session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()

def test_indicators_exclude_one_time():
    db = _session()
    db.add(Contract(title="A", amount_mrr=1000, amount_arr=12000, recurrence="monthly", status="actif"))
    db.add(Contract(title="B", amount_mrr=500, amount_arr=6000, recurrence="quarterly", status="actif"))
    # achat ponctuel : ne doit PAS compter dans MRR/ARR
    db.add(Contract(title="Achat", amount_mrr=0, amount_arr=34733, recurrence="one_time", status="actif"))
    db.commit()
    ind = indicators(db)
    assert ind["mrr"] == 1500          # 1000 + 500, one_time exclu
    assert ind["arr"] == 18000         # 12000 + 6000, one_time exclu
    assert ind["count"] == 3
