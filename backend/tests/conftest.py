import pytest

from loom import db


@pytest.fixture()
def session():
    db.init_db("sqlite:///:memory:")
    gen = db.get_session()
    s = next(gen)
    yield s
    try:
        next(gen)
    except StopIteration:
        pass
