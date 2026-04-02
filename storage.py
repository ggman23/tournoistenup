"""
Persistence layer: saves tournament data and detects new entries between runs.
"""

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


def _tournament_id(t: dict) -> str:
    """Unique identifier for a tournament."""
    return t.get("originalId") or t.get("id") or t.get("code", "")


def load_json(path: str) -> dict | list:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_json(path: str, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_new_tournaments(
    current: list[dict], previous_ids: set[str]
) -> list[dict]:
    """Return tournaments in `current` whose ID wasn't in the previous run."""
    new = []
    for t in current:
        tid = _tournament_id(t)
        if tid and tid not in previous_ids:
            new.append(t)
    return new


def update_storage(
    tournaments: list[dict],
    data_file: str,
    history_file: str,
) -> tuple[list[dict], set[str]]:
    """
    Load previous data, compute new tournaments, persist updated data.

    Returns (new_tournaments, all_current_ids).
    """
    # Load previous known IDs from history
    history = load_json(history_file)
    known_ids: set[str] = set(history.get("known_ids", []))

    # Find new ones
    new_tournaments = find_new_tournaments(tournaments, known_ids)

    # Build current ID set
    current_ids = {_tournament_id(t) for t in tournaments if _tournament_id(t)}

    # Update history
    all_known = known_ids | current_ids
    history["known_ids"] = sorted(all_known)
    history["last_run"] = datetime.utcnow().isoformat() + "Z"
    history["last_total"] = len(tournaments)
    save_json(history_file, history)

    # Save full current data
    payload = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "total": len(tournaments),
        "tournaments": tournaments,
    }
    save_json(data_file, payload)

    logger.info(
        "Stored %d tournaments. %d new since last run.",
        len(tournaments),
        len(new_tournaments),
    )
    return new_tournaments, current_ids
