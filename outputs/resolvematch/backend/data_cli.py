"""Validated JSON import/export. Replacement only into a fresh database."""

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .store import audit, db, initialize


class EngineerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=100)
    team: str = Field(min_length=1, max_length=80)
    skills: list[str] = Field(max_length=30)
    available: bool
    on_call: bool
    baseline_load: int = Field(ge=0, le=100)
    capacity: int = Field(ge=1, le=100)


class IncidentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    title: str = Field(min_length=5, max_length=500)
    description: str = Field(min_length=10, max_length=12000)
    product: str = Field(min_length=1, max_length=100)
    component: str = Field(min_length=1, max_length=100)
    team: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=100)
    severity: Literal["Low", "Medium", "High", "Critical"]
    resolved_by: str
    root_cause: str = Field(min_length=1, max_length=5000)
    resolution: str = Field(min_length=1, max_length=5000)
    resolution_minutes: int = Field(gt=0)


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engineers: list[EngineerRecord] = Field(min_length=1, max_length=5000)
    incidents: list[IncidentRecord] = Field(min_length=1, max_length=50000)


def import_data(path):
    source = Path(path)
    if source.stat().st_size > 50_000_000:
        raise ValueError("Dataset exceeds 50 MB")
    data = Dataset.model_validate_json(source.read_text())
    ids = {e.id for e in data.engineers}
    if len(ids) != len(data.engineers) or len({i.id for i in data.incidents}) != len(
        data.incidents
    ):
        raise ValueError("Duplicate record IDs")
    if any(i.resolved_by not in ids for i in data.incidents):
        raise ValueError("Incident references an unknown engineer")
    initialize()
    with db(True) as c:
        if c.execute("SELECT COUNT(*) FROM engineers").fetchone()[0]:
            raise ValueError(
                "Import requires a fresh database. Set RESOLVEMATCH_DB to a new path; existing data is never overwritten."
            )
        for engineer in data.engineers:
            e = engineer.model_dump()
            e["skills"] = json.dumps(e["skills"])
            c.execute(
                "INSERT INTO engineers VALUES(:id,:name,:team,:skills,:available,:on_call,:baseline_load,:capacity)",
                e,
            )
        for incident in data.incidents:
            c.execute(
                "INSERT INTO incidents VALUES(:id,:title,:description,:product,:component,:team,:category,:severity,:resolved_by,:root_cause,:resolution,:resolution_minutes)",
                incident.model_dump(),
            )
        c.execute("INSERT OR REPLACE INTO metadata VALUES('dataset','imported')")
        audit(
            c,
            "operator",
            "dataset.imported",
            details={
                "engineers": len(data.engineers),
                "incidents": len(data.incidents),
            },
        )


def export_data(path):
    with db() as c:
        engineers = []
        for r in c.execute("SELECT * FROM engineers"):
            e = dict(r)
            e["skills"] = json.loads(e["skills"])
            e["available"] = bool(e["available"])
            e["on_call"] = bool(e["on_call"])
            engineers.append(e)
        result = {
            "engineers": engineers,
            "incidents": [dict(r) for r in c.execute("SELECT * FROM incidents")],
        }
    with Path(path).open("x") as handle:
        json.dump(result, handle, indent=2)


def backup(path):
    destination = Path(path)
    if destination.exists():
        raise ValueError("Backup destination already exists")
    with db() as source, sqlite3.connect(destination) as target:
        source.backup(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["import", "export", "backup"])
    parser.add_argument("path")
    args = parser.parse_args()
    try:
        {"import": import_data, "export": export_data, "backup": backup}[args.action](
            args.path
        )
        print(args.action.capitalize() + " completed.")
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
