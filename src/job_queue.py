"""File d'attente et activité en direct.

- Une seule recherche à la fois (le pipeline ajuste des réglages globaux et
  occupe les GPU), premier arrivé, premier servi, avec la position de chacun.
- Qui fait quoi : nom de la personne dont la recherche tourne, noms des
  personnes en attente, personnes connectées (présence).
- Recherches abandonnées : si la page de la personne ne donne plus signe de
  vie, sa recherche est annulée au prochain appel au modèle, pour ne pas
  bloquer les suivants.
- Note d'état : message court affiché dans la jauge (« Gemini est surchargé,
  nouvel essai dans 20 s »).

Ce module n'est jamais rechargé entre deux questions : l'état est conservé.
"""

import threading
import time
from collections import deque
from typing import Dict, List, Optional

STALE_SECONDS = 60      # un ticket sans signe de vie depuis 1 min est considéré abandonné
ONLINE_SECONDS = 30     # présence : vu dans les 30 dernières secondes

_lock = threading.Lock()
_waiting = deque()                 # tickets en attente, dans l'ordre d'arrivée
_running: Optional[Dict] = None    # ticket de la recherche en cours
_presence: Dict[str, float] = {}   # identifiant -> dernier signe de vie


class SearchCancelled(RuntimeError):
    """La personne a quitté la page : sa recherche est arrêtée."""


def enter(user: str = "") -> dict:
    ticket = {"user": user or "anonyme", "seen": time.time(), "cancelled": False, "note": ""}
    with _lock:
        _waiting.append(ticket)
    return ticket


def _purge_stale() -> None:
    now = time.time()
    for ticket in list(_waiting):
        if now - ticket["seen"] > STALE_SECONDS:
            _waiting.remove(ticket)
    if _running is not None and now - _running["seen"] > STALE_SECONDS:
        _running["cancelled"] = True


def touch(ticket: dict) -> None:
    """Signe de vie de la page qui attend ou suit sa recherche."""
    with _lock:
        ticket["seen"] = time.time()


def try_start(ticket: dict) -> bool:
    global _running
    with _lock:
        ticket["seen"] = time.time()
        _purge_stale()
        if _running is None and _waiting and _waiting[0] is ticket:
            _waiting.popleft()
            ticket["since"] = time.time()
            _running = ticket
            return True
        return False


def finish(ticket: dict) -> None:
    global _running
    with _lock:
        if _running is ticket:
            _running = None


def leave(ticket: dict) -> None:
    with _lock:
        try:
            _waiting.remove(ticket)
        except ValueError:
            pass


def cancel(ticket: dict) -> None:
    with _lock:
        ticket["cancelled"] = True


def position(ticket: dict) -> int:
    """Nombre de recherches avant celle-ci (en cours comprise)."""
    with _lock:
        ticket["seen"] = time.time()
        for index, other in enumerate(_waiting):
            if other is ticket:
                return index + (1 if _running is not None else 0)
        return 0


# --- Utilisé par le pipeline (fil de la recherche en cours) -----------------

def check_cancelled() -> None:
    """Appelé avant chaque appel au modèle : arrête une recherche abandonnée."""
    with _lock:
        _purge_stale()
        cancelled = _running is not None and _running["cancelled"]
    if cancelled:
        raise SearchCancelled("Recherche arrêtée : la page qui l'avait lancée a été fermée.")


def set_note(note: str) -> None:
    with _lock:
        if _running is not None:
            _running["note"] = note


def note(ticket: dict) -> str:
    with _lock:
        return ticket.get("note", "")


# --- Présence et état global ---------------------------------------------

def seen_online(user: str) -> None:
    if user:
        with _lock:
            _presence[user] = time.time()


def status() -> Dict[str, object]:
    with _lock:
        _purge_stale()
        now = time.time()
        online: List[str] = sorted(u for u, t in _presence.items() if now - t < ONLINE_SECONDS)
        return {
            "running": _running is not None,
            "running_user": _running["user"] if _running else None,
            "running_since": _running.get("since") if _running else None,
            "waiting": len(_waiting),
            "waiting_users": [t["user"] for t in _waiting],
            "online": online,
        }
