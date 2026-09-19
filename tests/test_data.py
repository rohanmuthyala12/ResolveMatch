import json

import pytest

from backend import config
from backend.data_cli import backup, export_data, import_data
from backend.seed import seed
from backend.store import db


def test_import_export_validation_and_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "original.sqlite3")
    seed()
    path = tmp_path / "dataset.json"
    export_data(path)
    backup(tmp_path / "backup.sqlite3")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "imported.sqlite3")
    import_data(path)
    with db() as c:
        assert c.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 50
        assert (
            c.execute("SELECT value FROM metadata WHERE key='dataset'").fetchone()[0]
            == "imported"
        )
    with pytest.raises(ValueError, match="fresh database"):
        import_data(path)


def test_unknown_resolver_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "original.sqlite3")
    seed()
    path = tmp_path / "dataset.json"
    export_data(path)
    data = json.loads(path.read_text())
    data["incidents"][0]["resolved_by"] = "not-real"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "new.sqlite3")
    with pytest.raises(ValueError, match="unknown engineer"):
        import_data(path)


def test_demo_tickets_skip_empty_database_without_consuming_flag(tmp_path, monkeypatch):
    """An unseeded database must not mark the one-shot demo seeding as done."""
    from backend import config, seed as seed_module
    from backend.store import db, initialize

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "empty.sqlite3")
    initialize()
    assert seed_module.seed_demo_tickets() is False
    with db() as c:
        assert not c.execute(
            "SELECT 1 FROM metadata WHERE key='demo_tickets_v2'"
        ).fetchone()
    seed_module.seed()
    assert seed_module.seed_demo_tickets() is True
    with db() as c:
        assert c.execute("SELECT COUNT(*) FROM assignments").fetchone()[0] > 0
