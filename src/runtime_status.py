"""État de préparation de l'outil, partagé entre le démarrage et l'interface.

Au lancement d'une session partagée (Kaggle), le corpus et le modèle de
recherche se chargent en arrière-plan. L'interface s'affiche tout de suite et
lit cet état pour expliquer l'attente. Dans le notebook Colab, l'état est
« ready » dès le départ.

Ce module n'est jamais rechargé entre deux questions : l'état est conservé.
"""

import threading
import time

_lock = threading.Lock()
_state = {"state": "ready", "message": "", "since": time.time()}


def set_state(state: str, message: str = "") -> None:
    with _lock:
        # « since » ne repart de zéro qu'au changement d'état, pas à chaque
        # sous-étape : le visiteur voit depuis combien de temps il attend au total.
        if _state["state"] != state:
            _state["since"] = time.time()
        _state.update(state=state, message=message)


def get() -> dict:
    with _lock:
        return dict(_state)


def is_ready() -> bool:
    return get()["state"] == "ready"
