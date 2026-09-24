"""Construction du serveur web d'Ad-Dhakhira pour une session partagée (Kaggle).

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
    # Plusieurs visiteurs peuvent attendre en même temps : src/job_queue.py
    # garantit qu'une seule recherche tourne à la fois et affiche les positions.
    demo.queue(default_concurrency_limit=16)
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


# --------------------------------------------------------------------------
# Lien fixe : page GitHub Pages qui redirige vers le lien de la session
# --------------------------------------------------------------------------

REDIRECT_PAGE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Ad-Dhakhira</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 20px;
         background: #F8F3EA; color: #2A1B17; font-family: system-ui, "Segoe UI", sans-serif; }}
  main {{ width: min(440px, 100%); text-align: center; }}
  .panel {{ background: #3F0F18; color: #E6D5B0; padding: 34px 24px; outline: 1px solid rgba(184,149,90,.55);
            outline-offset: -9px; }}
  .ar {{ font-family: "Amiri", "Noto Naskh Arabic", serif; font-size: 2.8rem; color: #B8955A; margin: 0; }}
  h1 {{ font-family: Georgia, serif; font-weight: 500; font-size: 1.6rem; margin: 6px 0 0; color: #FBF4E6; }}
  .card {{ background: #FFFCF6; border: 1px solid #E4D7C3; border-top: 0; padding: 22px; line-height: 1.55; }}
  a.btn {{ display: inline-block; margin-top: 14px; padding: 12px 22px; background: #6B1D2A; color: #fff;
           text-decoration: none; font-weight: 600; }}
  .muted {{ color: #75655C; font-size: .9rem; }}
</style>
</head>
<body>
<main>
  <div class="panel"><p class="ar" lang="ar" dir="rtl">الذخيرة</p><h1>Assistant de recherche</h1></div>
  <div class="card" id="state"><p>Ouverture de l'outil…</p></div>
</main>
<script>
  var target = {target!r};
  var expires = new Date({expires!r});
  var box = document.getElementById("state");
  var until = expires.toLocaleTimeString("fr-FR", {{hour: "2-digit", minute: "2-digit"}});
  if (target && Date.now() < expires.getTime()) {{
    box.innerHTML = '<p>L\\'outil est ouvert jusqu\\'à <strong>' + until + '</strong>.</p>' +
      '<a class="btn" href="' + target + '">Ouvrir l\\'outil</a>' +
      '<p class="muted">Redirection automatique…</p>';
    setTimeout(function () {{ window.location.replace(target); }}, 1200);
  }} else {{
    box.innerHTML = '<p><strong>L\\'outil est hors ligne pour le moment.</strong></p>' +
      '<p class="muted">Il est ouvert par sessions. Revenez plus tard, ou contactez la personne ' +
      'qui vous a partagé ce lien.</p>';
  }}
</script>
</body>
</html>
"""


def publish_redirect_page(repo: str, token: str, target: str, hours: float,
                          branch: str = "gh-pages") -> str:
    """Met à jour la page fixe (GitHub Pages) pour qu'elle redirige vers target.

    repo : « propriétaire/dépôt ». token : jeton GitHub avec droit d'écriture
    sur le contenu du dépôt. target vide = page « hors ligne ». Renvoie
    l'adresse fixe à partager.
    """
    import base64
    import datetime

    import httpx

    api = f"https://api.github.com/repos/{repo}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    with httpx.Client(headers=headers, timeout=30) as client:
        ref = client.get(f"{api}/git/ref/heads/{branch}")
        if ref.status_code == 404:
            main = client.get(f"{api}/git/ref/heads/main")
            main.raise_for_status()
            client.post(f"{api}/git/refs", json={
                "ref": f"refs/heads/{branch}", "sha": main.json()["object"]["sha"],
            }).raise_for_status()
        else:
            ref.raise_for_status()
        expires = (datetime.datetime.now(datetime.timezone.utc)
                   + datetime.timedelta(hours=hours if target else 0)).isoformat()
        html = REDIRECT_PAGE.format(target=target, expires=expires)
        existing = client.get(f"{api}/contents/index.html", params={"ref": branch})
        payload = {
            "message": "Lien de session Ad-Dhakhira" if target else "Session Ad-Dhakhira terminée",
            "content": base64.b64encode(html.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if existing.status_code == 200:
            payload["sha"] = existing.json()["sha"]
        client.put(f"{api}/contents/index.html", json=payload).raise_for_status()
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/"
