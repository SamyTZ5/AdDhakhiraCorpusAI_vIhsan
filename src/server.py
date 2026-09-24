"""Construction du serveur web d'Ad-Dhakhira, commune à Modal et Kaggle.

build_app() assemble :
  - l'interface Gradio (src/web_app.py) ;
  - la page de connexion (src/login_page.py) si des comptes sont définis ;
  - le préchargement en arrière-plan du corpus et du modèle de recherche, avec
    un état lisible par l'interface (src/runtime_status.py).

Comptes : variable APP_USERS, une ligne « identifiant:motdepasse » par personne
(virgules acceptées). Compatibilité : APP_PASSWORD seul crée le compte « equipe ».
"""

import os
import threading
from typing import Callable, Optional


def log(message: str) -> None:
    print(f"[Ad-Dhakhira] {message}", flush=True)


def accounts_from_env() -> dict:
    from src.login_page import parse_users

    users = parse_users(os.environ.get("APP_USERS", ""))
    if not users and os.environ.get("APP_PASSWORD", "").strip():
        users = {"equipe": os.environ["APP_PASSWORD"].strip()}
        log("Compte unique « equipe » créé à partir de APP_PASSWORD (préférez APP_USERS).")
    return users


def preload(before: Optional[Callable[[], None]] = None) -> None:
    """Prépare l'outil ; l'interface lit l'avancement dans runtime_status."""
    from src import runtime_status

    try:
        if before is not None:
            runtime_status.set_state("loading", "Vérification du modèle et de l'index")
            before()

        from src import config
        from src.data_loader import load_chunks
        from src.embeddings import load_shared_embedding_model

        runtime_status.set_state("loading", "Préparation des 18 livres")
        log("Chargement du corpus…")
        load_chunks(str(config.JSON_INPUT_PATH))
        if getattr(config, "ENABLE_DENSE_RETRIEVAL", True):
            runtime_status.set_state("loading", "Chargement du modèle de recherche")
            log("Chargement du modèle de recherche…")
            load_shared_embedding_model(config.EMBEDDING_MODEL)
        runtime_status.set_state("ready")
        log("Outil prêt.")
    except Exception as exc:  # l'erreur est affichée aux visiteurs par le bandeau
        import traceback

        traceback.print_exc()
        runtime_status.set_state("error", str(exc))


def build_app(users: Optional[dict] = None, before_preload: Optional[Callable[[], None]] = None,
              background: bool = True):
    """Application FastAPI prête à servir. La page est servie immédiatement ;
    le préchargement se fait en arrière-plan (background=True)."""
    import gradio as gr
    from fastapi import FastAPI

    from src import ihsan_theme, runtime_status, web_app

    runtime_status.set_state("loading", "Démarrage")
    if background:
        threading.Thread(target=preload, args=(before_preload,), daemon=True).start()
    else:
        preload(before_preload)

    demo = web_app.build_demo()
    demo.queue(default_concurrency_limit=1)
    app = FastAPI()
    users = accounts_from_env() if users is None else users
    if users:
        from src.login_page import protect

        protect(app, users)
        log(f"Connexion requise : {len(users)} compte(s).")
    else:
        log("ATTENTION : aucun compte défini (APP_USERS), l'outil est ouvert à toute personne ayant le lien.")
    return gr.mount_gradio_app(
        app,
        demo,
        path="/",
        allowed_paths=web_app._allowed_paths(),
        **ihsan_theme.launch_kwargs(),
    )


def serve_in_background(app, port: int = 7860) -> None:
    """Lance le serveur (uvicorn) dans un fil d'exécution séparé."""
    import time

    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return
        time.sleep(0.2)
    raise RuntimeError("Le serveur web n'a pas démarré.")


def open_public_link(port: int = 7860) -> str:
    """Crée un lien public gradio.live vers le serveur local (valable 1 semaine,
    tant que la session tourne)."""
    import secrets
    from pathlib import Path

    import gradio.tunneling as tunneling
    from gradio.networking import setup_tunnel

    # Le programme du tunnel doit être sur un disque où il peut s'exécuter.
    local = Path("/tmp/gradio_frpc") / Path(tunneling.BINARY_PATH).name
    local.parent.mkdir(parents=True, exist_ok=True)
    tunneling.BINARY_FOLDER = local.parent
    tunneling.BINARY_PATH = str(local)
    return setup_tunnel("127.0.0.1", port, secrets.token_urlsafe(32), None, None)
