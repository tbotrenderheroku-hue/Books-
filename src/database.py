"""
Lightweight JSON-based storage for:
- registered user IDs (for broadcast)
- scheduled message deletions
- bot lock state
"""

import json
import os
import time
from pathlib import Path

DB_PATH = Path("data/db.json")

_defaults = {
    "users": [],
    "locked": False,
    "pending_deletes": [],   # [{chat_id, message_id, delete_at}]
}


def _load() -> dict:
    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _save(_defaults.copy())
    with open(DB_PATH) as f:
        data = json.load(f)
    # ensure all keys exist
    for k, v in _defaults.items():
        data.setdefault(k, v)
    return data


def _save(data: dict):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ─── USERS ───────────────────────────────────────────────────────────────────

def add_user(user_id: int):
    db = _load()
    if user_id not in db["users"]:
        db["users"].append(user_id)
        _save(db)


def get_all_users() -> list[int]:
    return _load()["users"]


# ─── LOCK ────────────────────────────────────────────────────────────────────

def set_locked(state: bool):
    db = _load()
    db["locked"] = state
    _save(db)


def is_locked() -> bool:
    return _load()["locked"]


# ─── AUTO-DELETE ─────────────────────────────────────────────────────────────

def schedule_delete(chat_id: int, message_id: int, hours: int = 24):
    db = _load()
    db["pending_deletes"].append({
        "chat_id": chat_id,
        "message_id": message_id,
        "delete_at": time.time() + hours * 3600
    })
    _save(db)


def pop_due_deletes() -> list[dict]:
    db = _load()
    now = time.time()
    due = [d for d in db["pending_deletes"] if d["delete_at"] <= now]
    db["pending_deletes"] = [d for d in db["pending_deletes"] if d["delete_at"] > now]
    _save(db)
    return due
