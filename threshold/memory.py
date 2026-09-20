"""What is normal for this door, and what isn't.

SQLite, because the baseline has to survive a restart and because a demo that
loses its history when you close the laptop is not a demo of memory.

Three anomalies, all computed deterministically from stored events:

  silence   — a stretch that is normally busy and today is empty. This is the
              one that matters for an older person living alone, and it is the
              only anomaly in the product that fires on *nothing happening*.
  novelty   — a subject at an hour it has never been seen at before.
  frequency — the same subject far more often than usual in a short window.

Seeded events are stored with source="seeded" and every query can exclude
them. Being able to prove, in the interface, which events were synthetic is
what makes it honest to demonstrate a baseline that took a fortnight to build
on a device that is two days old.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Iterable

from .events import Event

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    at REAL NOT NULL,
    trigger TEXT NOT NULL,
    subject TEXT NOT NULL,
    descriptors TEXT NOT NULL,
    action TEXT NOT NULL,
    point_x REAL, point_y REAL,
    zone_ids TEXT NOT NULL,
    dwell_s REAL NOT NULL,
    night INTEGER NOT NULL,
    confidence REAL NOT NULL,
    summary TEXT NOT NULL,
    source TEXT NOT NULL,
    provider TEXT NOT NULL,
    device_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_at ON events (at);
CREATE INDEX IF NOT EXISTS events_subject ON events (subject);
"""


@dataclass
class Anomaly:
    kind: str          # silence | novelty | frequency
    severity: str      # notice | concern
    message: str
    detail: dict[str, Any]


class Memory:
    def __init__(self, path: str = "threshold.db", *, clock=time.time):
        self.path = path
        self._clock = clock
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- writing -----------------------------------------------------------

    def record(self, event: Event) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO events
               (id, at, trigger, subject, descriptors, action, point_x, point_y, zone_ids,
                dwell_s, night, confidence, summary, source, provider, device_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event.id,
                event.at,
                event.trigger,
                event.subject,
                "|".join(event.descriptors),
                event.action,
                event.point[0] if event.point else None,
                event.point[1] if event.point else None,
                "|".join(event.zone_ids),
                event.dwell_s,
                1 if event.night else 0,
                event.confidence,
                event.summary,
                event.source,
                event.provider,
                event.device_id,
            ),
        )
        self._conn.commit()

    def record_many(self, events: Iterable[Event]) -> int:
        count = 0
        for event in events:
            self.record(event)
            count += 1
        return count

    def clear(self, *, source: str | None = None) -> int:
        cur = (
            self._conn.execute("DELETE FROM events WHERE source = ?", (source,))
            if source
            else self._conn.execute("DELETE FROM events")
        )
        self._conn.commit()
        return cur.rowcount

    # -- reading -----------------------------------------------------------

    def _row_to_event(self, row: sqlite3.Row) -> Event:
        point = (row["point_x"], row["point_y"]) if row["point_x"] is not None else None
        return Event(
            id=row["id"],
            at=row["at"],
            trigger=row["trigger"],
            subject=row["subject"],
            descriptors=tuple(d for d in row["descriptors"].split("|") if d),
            action=row["action"],
            point=point,
            zone_ids=tuple(z for z in row["zone_ids"].split("|") if z),
            dwell_s=row["dwell_s"],
            night=bool(row["night"]),
            confidence=row["confidence"],
            summary=row["summary"],
            source=row["source"],
            provider=row["provider"],
            device_id=row["device_id"],
        )

    def recent(self, limit: int = 50, *, include_seeded: bool = True) -> list[Event]:
        sql = "SELECT * FROM events"
        if not include_seeded:
            sql += " WHERE source != 'seeded'"
        sql += " ORDER BY at DESC LIMIT ?"
        return [self._row_to_event(r) for r in self._conn.execute(sql, (limit,))]

    def count(self, *, source: str | None = None) -> int:
        if source:
            return self._conn.execute("SELECT COUNT(*) FROM events WHERE source = ?", (source,)).fetchone()[0]
        return self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def between(self, start: float, end: float) -> list[Event]:
        rows = self._conn.execute("SELECT * FROM events WHERE at >= ? AND at < ? ORDER BY at", (start, end))
        return [self._row_to_event(r) for r in rows]

    # -- the baseline ------------------------------------------------------

    def baseline(self, *, days: int = 21) -> dict[str, Any]:
        """Counts per weekday-hour bucket, and per subject.

        Deliberately simple statistics. A neural model of a household's rhythm
        from a fortnight of data would be a fiction with a confidence interval
        attached; counting is honest about what it knows.
        """
        since = self._clock() - days * 86400
        buckets: dict[str, int] = {}
        subject_hours: dict[str, set[int]] = {}
        days_seen: set[str] = set()

        for row in self._conn.execute("SELECT * FROM events WHERE at >= ? ORDER BY at", (since,)):
            lt = time.localtime(row["at"])
            key = f"{lt.tm_wday}:{lt.tm_hour}"
            buckets[key] = buckets.get(key, 0) + 1
            days_seen.add(time.strftime("%Y-%m-%d", lt))
            subject_hours.setdefault(row["subject"], set()).add(lt.tm_hour)

        weeks = max(1, len(days_seen) / 7)
        return {
            "buckets": buckets,
            "per_week": {k: v / weeks for k, v in buckets.items()},
            "subject_hours": {k: sorted(v) for k, v in subject_hours.items()},
            "days_observed": len(days_seen),
            "total": sum(buckets.values()),
        }

    # -- anomalies ---------------------------------------------------------

    def check_event(self, event: Event, *, baseline: dict[str, Any] | None = None) -> list[Anomaly]:
        base = baseline or self.baseline()
        found: list[Anomaly] = []
        lt = time.localtime(event.at)

        known_hours = base["subject_hours"].get(event.subject, [])
        if known_hours and lt.tm_hour not in known_hours and event.subject in ("person", "vehicle"):
            found.append(
                Anomaly(
                    kind="novelty",
                    severity="notice",
                    message=(
                        f"This is the first time a {event.subject} has been at the door "
                        f"around {lt.tm_hour:02d}:00."
                    ),
                    detail={"hour": lt.tm_hour, "known_hours": known_hours},
                )
            )

        hour_ago = event.at - 3600
        same = [
            e
            for e in self.between(hour_ago, event.at + 1)
            if e.subject == event.subject and e.id != event.id
        ]
        if len(same) >= 3:
            found.append(
                Anomaly(
                    kind="frequency",
                    severity="concern",
                    message=f"That is {len(same) + 1} visits by a {event.subject} within an hour.",
                    detail={"count": len(same) + 1, "window_s": 3600},
                )
            )
        return found

    def check_silence(self, *, now: float | None = None, min_expected: float = 0.8) -> Anomaly | None:
        """Nothing happened in a window where something normally does.

        Two conditions, and both are needed. The bucket must have fired in
        most weeks (`min_expected`, per week), *and* it must have happened at
        least twice — because a bucket seen once in a fortnight computes to
        roughly one a week and would otherwise look like a routine. That was a
        real false positive, caught by the test that now guards it.
        """
        now = now or self._clock()
        base = self.baseline()
        if base["days_observed"] < 5:
            return None  # too little history to claim anything is unusual

        lt = time.localtime(now)
        key = f"{lt.tm_wday}:{lt.tm_hour}"
        expected = base["per_week"].get(key, 0.0)
        if base["buckets"].get(key, 0) < 2 or expected < min_expected:
            return None

        start = now - (lt.tm_min * 60 + lt.tm_sec)
        if self.between(start, now + 1):
            return None

        weekday = time.strftime("%A", lt)
        return Anomaly(
            kind="silence",
            severity="concern",
            message=(
                f"Nothing has happened at the door this hour. On a normal {weekday} "
                f"around {lt.tm_hour:02d}:00 there are usually about {expected:.0f}."
            ),
            detail={"bucket": key, "expected_per_week": expected},
        )
