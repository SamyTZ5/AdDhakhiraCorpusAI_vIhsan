"""Point d'entrée Hugging Face Spaces pour Ad-Dhakhira.

Ce Space ne contient que ce fichier, requirements.txt et README.md. Au
démarrage, il :
  1. récupère le code et le corpus depuis GitHub ;
  2. télécharge l'index de recherche depuis un dépôt de données Hugging Face ;
  3. charge le corpus et le modèle de recherche en mémoire ;
  4. lance l'interface, protégée par mot de passe si APP_PASSWORD est défini.

Réglages (onglet Settings du Space) :
  Secrets   : GEMINI_API_KEY (obligatoire), APP_PASSWORD (recommandé)
  Variables : ADDHAKHIRA_INDEX_REPO (obligatoire, ex. "pseudo/ad-dhakhira-index")
              GEMINI_MODEL, ADDHAKHIRA_REPO, ADDHAKHIRA_BRANCH,
              ADDHAKHIRA_EMBEDDING_MODEL (facultatifs)
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_URL = os.environ.get("ADDHAKHIRA_REPO", "https://github.com/SamyTZ5/AdDhakhiraCorpusAI_vIhsan.git")
BRANCH = os.environ.get("ADDHAKHIRA_BRANCH", "main")
INDEX_REPO = os.environ.get("ADDHAKHIRA_INDEX_REPO", "").strip()
EMBEDDING_MODEL = os.environ.get("ADDHAKHIRA_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

WORK = Path.home() / "addhakhira"
REPO_DIR = WORK / "repo"
INDEX_DIR = WORK / "vector_indexes"


def log(message: str) -> None:
    print(f"[Ad-Dhakhira] {message}", flush=True)


def run(cmd, cwd=None) -> None:
    log("$ " + " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def fetch_code() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    if (REPO_DIR / ".git").exists():
        run(["git", "fetch", "--depth", "1", "origin", BRANCH], cwd=REPO_DIR)
        run(["git", "reset", "--hard", f"origin/{BRANCH}"], cwd=REPO_DIR)
    else:
        run(["git", "clone", "--depth", "1", "-b", BRANCH, REPO_URL, str(REPO_DIR)])


def fetch_index() -> None:
    if not INDEX_REPO:
        raise SystemExit(
            "La variable ADDHAKHIRA_INDEX_REPO n'est pas définie. Ajoutez-la dans "
            "Settings → Variables and secrets (exemple : pseudo/ad-dhakhira-index)."
        )
    from huggingface_hub import hf_hub_download
    from src.vector_index import index_dir_for

    folder = index_dir_for(INDEX_DIR, EMBEDDING_MODEL, "faiss")
    for filename in ("signature.json", "index.faiss"):
        hf_hub_download(
            repo_id=INDEX_REPO,
            repo_type="dataset",
            filename=f"{folder.name}/{filename}",
            local_dir=str(folder.parent),
        )
    log(f"Index prêt : {folder}")


def write_config() -> None:
    template = (REPO_DIR / "src" / "config_template.py").read_text(encoding="utf-8")
    overrides = f'''

# --- Réglages Hugging Face Spaces (générés par app.py) ---
LLM_BACKEND = "gemini_api"
GEMINI_API_KEY = ""  # lue depuis le secret GEMINI_API_KEY, jamais écrite ici
MODEL_EXTRACTOR_PATH = {GEMINI_MODEL!r}
MODEL_REASONER_PATH = {GEMINI_MODEL!r}
EMBEDDING_MODEL = {EMBEDDING_MODEL!r}
EMBEDDING_INDEX_DIR = Path({str(INDEX_DIR)!r})
ENABLE_DENSE_RETRIEVAL = True
VECTOR_INDEX_BACKEND = "faiss"
'''
    (REPO_DIR / "src" / "config.py").write_text(template + overrides, encoding="utf-8")


def main() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        log("ATTENTION : le secret GEMINI_API_KEY est absent, chaque visiteur devra saisir sa propre clé.")
    os.environ.setdefault("ADDHAKHIRA_BACKENDS", "gemini_api")
    os.environ.setdefault("GEMINI_MODEL", GEMINI_MODEL)

    fetch_code()
    os.chdir(REPO_DIR)
    sys.path.insert(0, str(REPO_DIR))
    write_config()
    fetch_index()

    # Préchargement : la première question n'attend ni le corpus ni le modèle.
    from src import config
    from src.data_loader import load_chunks
    from src.embeddings import load_shared_embedding_model

    log("Chargement du corpus…")
    load_chunks(str(config.JSON_INPUT_PATH))
    log("Chargement du modèle de recherche…")
    load_shared_embedding_model(EMBEDDING_MODEL)

    from src import ihsan_theme, web_app

    demo = web_app.build_demo()
    demo.queue(default_concurrency_limit=1)
    password = os.environ.get("APP_PASSWORD", "").strip()
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", "7860")),
        auth=(lambda _user, given: given == password) if password else None,
        auth_message="Ad-Dhakhira : saisissez n'importe quel identifiant et le mot de passe communiqué.",
        allowed_paths=web_app._allowed_paths(),
        **ihsan_theme.launch_kwargs(),
    )


if __name__ == "__main__":
    main()
