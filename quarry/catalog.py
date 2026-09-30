"""The databases Quarry can query, with their schema metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

INFO = {
    "formula_1": ("Formula 1", "Races, drivers, constructors, results and lap times, 1950 to 2017."),
    "california_schools": (
        "California schools",
        "Every California school with enrolment, free-meal and SAT score data.",
    ),
    "thrombosis_prediction": (
        "Thrombosis prediction",
        "Patient records and lab tests from a hospital collagen-disease study.",
    ),
    "toxicology": ("Toxicology", "Molecules, atoms and bonds, labelled carcinogenic or not."),
    "student_club": ("Student club", "A university club's members, events, budgets, expenses and income."),
    "superhero": ("Superheroes", "Superheroes with their powers, attributes, publishers and appearance."),
    "card_games": ("Card games", "Magic: The Gathering cards, sets, rulings and legalities."),
    "codebase_community": ("Codebase community", "A Q&A site: posts, comments, users, votes and badges."),
    "debit_card_specializing": ("Debit cards", "Gas-station customers, transactions and monthly consumption."),
    "european_football_2": ("European football", "Matches, teams, players and FIFA ratings across European leagues."),
    "financial": ("Czech bank", "Accounts, clients, loans, cards and transactions from a Czech bank."),
}


@dataclass
class Database:
    db_id: str
    folder: Path
    raw_dir: Path

    @property
    def title(self) -> str:
        return INFO.get(self.db_id, (self.db_id.replace("_", " ").title(), ""))[0]

    @property
    def summary(self) -> str:
        return INFO.get(self.db_id, ("", ""))[1]

    @cached_property
    def schema(self) -> dict:
        return json.loads((self.folder / "schema.json").read_text(encoding="utf-8"))

    @property
    def path(self) -> Path:
        local = self.folder / f"{self.db_id}.sqlite"
        return local if local.exists() else self.raw_dir / "dev_databases" / self.db_id / f"{self.db_id}.sqlite"

    @property
    def values_path(self) -> Path:
        return self.folder / "values.sqlite"

    @property
    def available(self) -> bool:
        return self.path.exists()

    def table(self, name: str) -> dict | None:
        return next((t for t in self.schema["tables"] if t["name"].lower() == name.lower()), None)


class Catalog:
    def __init__(self, data_dir: Path, raw_dir: Path):
        self.data_dir, self.raw_dir = Path(data_dir), Path(raw_dir)
        self._dbs: dict[str, Database] = {}
        if self.data_dir.exists():
            for f in sorted(self.data_dir.glob("*/schema.json")):
                db = Database(f.parent.name, f.parent, self.raw_dir)
                self._dbs[db.db_id] = db

    def get(self, db_id: str) -> Database | None:
        return self._dbs.get(db_id)

    def all(self, available_only: bool = True) -> list[Database]:
        return [d for d in self._dbs.values() if d.available or not available_only]
