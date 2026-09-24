"""Déploiement d'Ad-Dhakhira sur Modal (https://modal.com).

Architecture :
  - un GPU T4 fait tourner le modèle de recherche Qwen3-Embedding-4B ;
  - Gemini (API) extrait les mots-clés et rédige la synthèse ;
  - le modèle et l'index sont gardés dans un Volume Modal, téléchargés une seule fois ;
  - l'application s'éteint après 10 minutes sans visite et ne coûte alors rien.

Prérequis : un secret Modal nommé « addhakhira » contenant GEMINI_API_KEY et
APP_PASSWORD. Le plus simple est de passer par l'Étape 4 du notebook Colab,
qui crée le secret, prépare le Volume et déploie.

En ligne de commande, depuis la racine du dépôt :
    modal run modal_app.py::prepare_assets   # une fois : modèle + index
    modal deploy modal_app.py                # publie l'application
"""

import os
from pathlib import Path

try:
    import modal
except ImportError:  # permet de tester create_web_app() sans Modal
    modal = None

APP_NAME = "ad-dhakhira"
SECRET_NAME = "addhakhira"
VOLUME_NAME = "addhakhira-data"

CODE_DIR = Path(os.environ.get("ADDHAKHIRA_CODE_DIR", "/root/addhakhira"))
DATA_DIR = Path(os.environ.get("ADDHAKHIRA_DATA_DIR", "/data"))
EMBEDDING_REPO = "Qwen/Qwen3-Embedding-4B"
EMBEDDING_DIR = DATA_DIR / "models" / "Qwen__Qwen3-Embedding-4B"
INDEX_ROOT = DATA_DIR / "vector_indexes"
PREBUILT_INDEX_REPO = "userzh92/addhakhira-faiss-index"
PREBUILT_INDEX_PATH = "Qwen__Qwen3-Embedding-4B"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")


def log(message: str) -> None:
    print(f"[Ad-Dhakhira] {message}", flush=True)


def _use_code_dir() -> None:
    import sys

    os.chdir(CODE_DIR)
    if str(CODE_DIR) not in sys.path:
        sys.path.insert(0, str(CODE_DIR))


def ensure_assets() -> bool:
    """Télécharge le modèle de recherche et l'index s'ils manquent. Renvoie True si
    quelque chose a été téléchargé (le Volume doit alors être enregistré)."""
    from huggingface_hub import hf_hub_download, snapshot_download

    _use_code_dir()
    changed = False
    if not (EMBEDDING_DIR / "config.json").exists():
        log(f"Téléchargement du modèle de recherche vers {EMBEDDING_DIR}…")
        snapshot_download(repo_id=EMBEDDING_REPO, local_dir=str(EMBEDDING_DIR))
        changed = True

    # Le modèle doit exister avant ce calcul : le dossier de l'index porte son nom.
    from src.vector_index import index_dir_for

    folder = index_dir_for(INDEX_ROOT, str(EMBEDDING_DIR), "faiss")
    for filename in ("signature.json", "index.faiss"):
        if not (folder / filename).exists():
            log(f"Téléchargement de l'index : {filename}…")
            hf_hub_download(
                repo_id=PREBUILT_INDEX_REPO,
                repo_type="dataset",
                filename=f"{PREBUILT_INDEX_PATH}/{filename}",
                local_dir=str(folder.parent),
            )
            changed = True
    log(f"Modèle et index prêts ({folder}).")
    return changed


def write_config() -> None:
    template = (CODE_DIR / "src" / "config_template.py").read_text(encoding="utf-8")
    overrides = f'''

# --- Réglages Modal (générés par modal_app.py) ---
LLM_BACKEND = "gemini_api"
GEMINI_API_KEY = ""  # lue depuis le secret Modal, jamais écrite ici
MODEL_EXTRACTOR_PATH = {GEMINI_MODEL!r}
MODEL_REASONER_PATH = {GEMINI_MODEL!r}
EMBEDDING_MODEL = {str(EMBEDDING_DIR)!r}
EMBEDDING_INDEX_DIR = Path({str(INDEX_ROOT)!r})
ENABLE_DENSE_RETRIEVAL = True
VECTOR_INDEX_BACKEND = "faiss"
'''
    (CODE_DIR / "src" / "config.py").write_text(template + overrides, encoding="utf-8")


def create_web_app(commit_volume=None):
    """Construit l'application web (FastAPI + Gradio), prête à servir."""
    os.environ.setdefault("ADDHAKHIRA_BACKENDS", "gemini_api")
    os.environ.setdefault("GEMINI_MODEL", GEMINI_MODEL)
    if not os.environ.get("GEMINI_API_KEY"):
        log("ATTENTION : GEMINI_API_KEY absente du secret, chaque visiteur devra saisir sa clé.")

    _use_code_dir()
    write_config()
    if ensure_assets() and commit_volume is not None:
        commit_volume()

    # Préchargement : la première question n'attend ni le corpus ni le modèle.
    from src import config
    from src.data_loader import load_chunks
    from src.embeddings import load_shared_embedding_model

    log("Chargement du corpus…")
    load_chunks(str(config.JSON_INPUT_PATH))
    log("Chargement du modèle de recherche…")
    load_shared_embedding_model(config.EMBEDDING_MODEL)

    import gradio as gr
    from fastapi import FastAPI

    from src import ihsan_theme, web_app

    demo = web_app.build_demo()
    demo.queue(default_concurrency_limit=1)
    password = os.environ.get("APP_PASSWORD", "").strip()
    log("Application prête.")
    return gr.mount_gradio_app(
        FastAPI(),
        demo,
        path="/",
        auth=(lambda _user, given: given == password) if password else None,
        auth_message="Ad-Dhakhira : saisissez n'importe quel identifiant et le mot de passe communiqué.",
        allowed_paths=web_app._allowed_paths(),
        **ihsan_theme.launch_kwargs(),
    )


if modal is not None:
    app = modal.App(APP_NAME)
    volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

    image = (
        modal.Image.debian_slim(python_version="3.12")
        .apt_install("git")
        .pip_install(
            "torch",
            "transformers==5.10.1",
            "sentence-transformers==5.3.0",
            "huggingface-hub==1.16.1",
            "tokenizers==0.22.2",
            "safetensors==0.6.2",
            "accelerate==1.7.0",
            "numpy==2.2.6",
            "faiss-cpu==1.13.2",
            "rank-bm25==0.2.2",
            "google-genai==2.10.0",
            "openai==2.28.0",
            "anthropic==0.82.0",
            "httpx==0.28.1",
            "gradio==6.15.1",
            "fastapi",
        )
        .env(
            {
                "ADDHAKHIRA_BACKENDS": "gemini_api",
                "HF_HOME": str(DATA_DIR / "hf_cache"),
                "TOKENIZERS_PARALLELISM": "false",
            }
        )
        # Le code et les livres sont copiés depuis le dépôt local au moment du
        # déploiement. src/config.py (qui peut contenir une clé) n'est jamais envoyé.
        .add_local_dir("src", remote_path=str(CODE_DIR / "src"), copy=True,
                       ignore=["config.py", "**/__pycache__/**"])
        .add_local_dir("database", remote_path=str(CODE_DIR / "database"), copy=True)
    )

    @app.function(image=image, volumes={str(DATA_DIR): volume}, timeout=60 * 60)
    def prepare_assets() -> None:
        """À lancer une fois : télécharge le modèle (8 Go) et l'index dans le Volume."""
        if ensure_assets():
            volume.commit()

    @app.function(
        image=image,
        gpu="T4",
        memory=8192,
        volumes={str(DATA_DIR): volume},
        secrets=[modal.Secret.from_name(SECRET_NAME)],
        timeout=60 * 60,
        scaledown_window=10 * 60,  # s'éteint après 10 min sans visite
        max_containers=1,          # une seule instance : file d'attente partagée
    )
    @modal.concurrent(max_inputs=100)
    @modal.asgi_app()
    def web():
        return create_web_app(commit_volume=volume.commit)
