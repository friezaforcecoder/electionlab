from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from collections.abc import Iterator
from typing import Any, Iterable

from .settings import SettingsManager


class KnowledgeVault:
    def __init__(self, settings: SettingsManager):
        self.settings = settings
        self.db_path = settings.path_for("KnowledgeVault") / "electionlab.sqlite3"
        self._init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE,
                    profile_type TEXT NOT NULL DEFAULT 'person',
                    source_type TEXT NOT NULL DEFAULT 'user',
                    party TEXT,
                    home_state TEXT,
                    birth_year INTEGER,
                    career TEXT,
                    office_years TEXT,
                    ideology REAL DEFAULT 0,
                    national_appeal REAL DEFAULT 0,
                    charisma REAL DEFAULT 50,
                    debate_skill REAL DEFAULT 50,
                    experience REAL DEFAULT 50,
                    name_recognition REAL DEFAULT 50,
                    known_positions_json TEXT DEFAULT '{}',
                    inferred_positions_json TEXT DEFAULT '{}',
                    controversies_json TEXT DEFAULT '[]',
                    sources_json TEXT DEFAULT '[]',
                    confidence REAL DEFAULT 0.5,
                    profile_status TEXT DEFAULT 'starter',
                    snapshot_date TEXT,
                    locked INTEGER DEFAULT 0,
                    photo_path TEXT,
                    photo_source_url TEXT,
                    raw_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_profiles_name ON profiles(normalized_name);

                CREATE TABLE IF NOT EXISTS profile_tombstones (
                    normalized_name TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    deleted_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS data_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            # Pre-0.4 databases do not have photo columns. Keep upgrades in-place.
            cols = {r[1] for r in conn.execute("PRAGMA table_info(profiles)").fetchall()}
            if "photo_path" not in cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN photo_path TEXT")
            if "photo_source_url" not in cols:
                conn.execute("ALTER TABLE profiles ADD COLUMN photo_source_url TEXT")

    @staticmethod
    def normalize(name: str) -> str:
        return " ".join(name.lower().strip().split())

    def upsert_profile(self, profile: dict[str, Any], overwrite_locked: bool = False) -> None:
        now = datetime.now(timezone.utc).isoformat()
        name = profile["canonical_name"].strip()
        norm = self.normalize(name)
        existing = self.get_profile(name)
        if existing and existing.get("locked") and not overwrite_locked:
            return

        # Explicitly adding/researching a deleted name restores it.
        with self.connect() as conn:
            conn.execute("DELETE FROM profile_tombstones WHERE normalized_name=?", (norm,))

        row = {
            "canonical_name": name,
            "normalized_name": norm,
            "profile_type": profile.get("profile_type", "person"),
            "source_type": profile.get("source_type", "user"),
            "party": profile.get("party"),
            "home_state": profile.get("home_state"),
            "birth_year": profile.get("birth_year"),
            "career": profile.get("career"),
            "office_years": profile.get("office_years"),
            "ideology": float(profile.get("ideology", 0) or 0),
            "national_appeal": float(profile.get("national_appeal", 0) or 0),
            "charisma": float(profile.get("charisma", 50) or 50),
            "debate_skill": float(profile.get("debate_skill", 50) or 50),
            "experience": float(profile.get("experience", 50) or 50),
            "name_recognition": float(profile.get("name_recognition", 50) or 50),
            "known_positions_json": json.dumps(profile.get("known_positions", {})),
            "inferred_positions_json": json.dumps(profile.get("inferred_positions", {})),
            "controversies_json": json.dumps(profile.get("controversies", [])),
            "sources_json": json.dumps(profile.get("sources", [])),
            "confidence": float(profile.get("confidence", 0.5) or 0.5),
            "profile_status": profile.get("profile_status", "starter"),
            "snapshot_date": profile.get("snapshot_date"),
            "locked": 1 if profile.get("locked") else 0,
            "photo_path": profile.get("photo_path") or (existing or {}).get("photo_path"),
            "photo_source_url": profile.get("photo_source_url") or (existing or {}).get("photo_source_url"),
            "raw_json": json.dumps(profile, ensure_ascii=False),
            "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
        }
        columns = list(row)
        placeholders = ",".join("?" for _ in columns)
        updates = ",".join(f"{c}=excluded.{c}" for c in columns if c not in {"created_at", "normalized_name"})
        with self.connect() as conn:
            conn.execute(
                f"""INSERT INTO profiles ({','.join(columns)}) VALUES ({placeholders})
                ON CONFLICT(normalized_name) DO UPDATE SET {updates}""",
                [row[c] for c in columns],
            )

    def get_profile(self, name: str) -> dict[str, Any] | None:
        norm = self.normalize(name)
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM profiles WHERE normalized_name=?", (norm,)).fetchone()
        return self._decode(row) if row else None

    def list_profiles(self, search: str = "", limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if search.strip():
                q = f"%{self.normalize(search)}%"
                rows = conn.execute(
                    "SELECT * FROM profiles WHERE normalized_name LIKE ? ORDER BY canonical_name LIMIT ?",
                    (q, limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM profiles ORDER BY canonical_name LIMIT ?", (limit,)).fetchall()
        return [self._decode(r) for r in rows]

    def delete_profile(self, name: str, remember_deletion: bool = True) -> bool:
        """Delete a local profile.

        Built-in starter data is seeded on install/update. A tombstone prevents a profile the
        user deliberately deleted from silently returning during a later seed refresh. Explicitly
        re-adding/researching the person clears the tombstone.
        """
        norm = self.normalize(name)
        existing = self.get_profile(name)
        if not existing:
            return False
        with self.connect() as conn:
            conn.execute("DELETE FROM profiles WHERE normalized_name=?", (norm,))
            if remember_deletion:
                conn.execute(
                    "INSERT INTO profile_tombstones(normalized_name,canonical_name,deleted_at) VALUES(?,?,?) "
                    "ON CONFLICT(normalized_name) DO UPDATE SET canonical_name=excluded.canonical_name, deleted_at=excluded.deleted_at",
                    (norm, existing.get("canonical_name") or name, datetime.now(timezone.utc).isoformat()),
                )
        return True

    def update_photo(self, name: str, photo_path: str, source_url: str | None = None) -> None:
        norm = self.normalize(name)
        with self.connect() as conn:
            conn.execute(
                "UPDATE profiles SET photo_path=?, photo_source_url=?, updated_at=? WHERE normalized_name=?",
                (photo_path, source_url, datetime.now(timezone.utc).isoformat(), norm),
            )

    def seed_profiles(self, profiles: Iterable[dict[str, Any]], seed_version: str) -> int:
        """Install or safely refresh the built-in starter pack.

        0.10 deliberately distinguishes *starter-owned* records from user/research-owned
        records. A new ElectionLab starter pack may update an existing profile only when
        that profile is still a built-in starter (source_type == ``built_in`` and its
        status starts with ``starter``). Custom profiles, web/OpenAI/local-AI enriched
        profiles, locked records, and deliberate deletions are never replaced. Cached
        portraits are preserved by :meth:`upsert_profile`.
        """
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM data_metadata WHERE key='seed_version'").fetchone()
            if row and row[0] == seed_version:
                return 0
            tombstones = {r[0] for r in conn.execute("SELECT normalized_name FROM profile_tombstones").fetchall()}
        changed = 0
        for p in profiles:
            norm = self.normalize(p["canonical_name"])
            if norm in tombstones:
                continue
            existing = self.get_profile(p["canonical_name"])
            if existing is None:
                self.upsert_profile(p)
                changed += 1
                continue
            source = str(existing.get("source_type") or "")
            status = str(existing.get("profile_status") or "")
            if existing.get("locked"):
                continue
            if source == "built_in" and status.startswith("starter"):
                # This record is still owned by the starter pack, so it is safe to
                # refresh its bundled model inputs. Preserve user-acquired media.
                refreshed = dict(p)
                refreshed["photo_path"] = existing.get("photo_path")
                refreshed["photo_source_url"] = existing.get("photo_source_url")
                self.upsert_profile(refreshed)
                changed += 1
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO data_metadata(key,value) VALUES('seed_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (seed_version,),
            )
        return changed

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for key in ["known_positions_json", "inferred_positions_json", "controversies_json", "sources_json", "raw_json"]:
            raw = d.pop(key, None)
            out_key = key.replace("_json", "")
            try:
                d[out_key] = json.loads(raw or ("[]" if key in {"controversies_json", "sources_json"} else "{}"))
            except Exception:
                d[out_key] = [] if key in {"controversies_json", "sources_json"} else {}
        d["locked"] = bool(d.get("locked"))
        return d
