from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import list_platforms
from app.db.session import Base
from app.models.models import Platform


def test_list_platforms_returns_sorted_platform_names():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, future=True)
    Base.metadata.create_all(engine)

    with Session() as db:
        db.add_all([Platform(canonical_name="Wealthsimple"), Platform(canonical_name="CIBC")])
        db.commit()

        assert list_platforms(db) == ["CIBC", "Wealthsimple"]
