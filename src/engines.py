"""Moteurs de réponse disponibles et règles d'affichage.

Règle unique : un moteur n'apparaît dans la liste que s'il peut réellement
fonctionner ici.
  - Moteurs locaux (vLLM) : il faut une carte graphique, vLLM installé et les
    modèles présents sur le disque. Sur un hébergement sans GPU, ils sont
    listés dans l'onglet Paramètres avec la raison de leur absence.
  - Moteurs en ligne (Gemini, ChatGPT, Claude) : il faut une clé, fournie
    par le serveur (secret d'hébergement) ou par l'utilisateur dans l'onglet
    Paramètres. Les clés de l'utilisateur restent dans son navigateur et ne
    sont transmises au serveur que le temps d'une question.
"""

import importlib.util
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

LOCAL_ENGINES = {
    "default": {
        "label": "Modèles locaux · Gemma 4 12B + Qwen3.6 35B",
        "config": ("MODEL_EXTRACTOR_PATH", "MODEL_REASONER_PATH"),
        "hint": "Nécessite une grosse carte graphique (A100 ou équivalent).",
    },
    "lite_version": {
        "label": "Version légère locale · Qwen2.5 7B",
        "config": ("LITE_MODEL_PATH",),
        "hint": "Nécessite une carte graphique d'au moins 16 Go (T4 de Colab par exemple).",
    },
}

API_ENGINES = {
    "gemini_api": {
        "label": "Gemini",
        "provider": "Google Gemini",
        "key_name": "GEMINI_API_KEY",
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-3.5-flash-lite",
        "key_help": "Clé Google AI Studio (aistudio.google.com)",
    },
    "openai_api": {
        "label": "ChatGPT",
        "provider": "OpenAI",
        "key_name": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "default_model": "gpt-4.1",
        "key_help": "Clé OpenAI Platform (platform.openai.com), commence par sk-",
    },
    "anthropic_api": {
        "label": "Claude",
        "provider": "Anthropic",
        "key_name": "ANTHROPIC_API_KEY",
        "model_env": "ANTHROPIC_MODEL",
        "default_model": "claude-sonnet-5",
        "key_help": "Clé Claude Platform (platform.claude.com), commence par sk-ant-",
    },
}

ENGINE_ORDER = ["gemini_api", "anthropic_api", "openai_api", "lite_version", "default"]


def _config_value(name: str, default=None):
    try:
        from src import config

        return getattr(config, name, default)
    except Exception:
        return default


def default_model(engine_id: str) -> str:
    info = API_ENGINES[engine_id]
    return os.environ.get(info["model_env"]) or info["default_model"]


def server_key(engine_id: str) -> str:
    key_name = API_ENGINES[engine_id]["key_name"]
    return str(_config_value(key_name, "") or "").strip() or os.environ.get(key_name, "").strip()


def user_entry(engine_id: str, settings: Optional[Dict]) -> Dict[str, str]:
    entry = (settings or {}).get(engine_id) or {}
    return {"key": str(entry.get("key") or "").strip(), "model": str(entry.get("model") or "").strip()}


def local_status(engine_id: str) -> Tuple[bool, str]:
    """(disponible, raison) pour un moteur local."""
    try:
        import torch

        has_gpu = torch.cuda.is_available()
    except Exception:
        has_gpu = False
    if not has_gpu:
        return False, "Indisponible sur ce serveur : il n'a pas de carte graphique."
    if importlib.util.find_spec("vllm") is None:
        return False, "Indisponible sur ce serveur : vLLM n'est pas installé."
    for name in LOCAL_ENGINES[engine_id]["config"]:
        path = str(_config_value(name, "") or "")
        if not path or not Path(path).exists():
            return False, "Indisponible sur ce serveur : le modèle n'est pas téléchargé."
    return True, "Disponible."


def available_engines(settings: Optional[Dict] = None) -> List[Tuple[str, str]]:
    """Choix (libellé, identifiant) à afficher dans la liste des moteurs."""
    choices = []
    for engine_id in ENGINE_ORDER:
        if engine_id in API_ENGINES:
            if user_entry(engine_id, settings)["key"]:
                choices.append((f"{API_ENGINES[engine_id]['label']} · votre clé", engine_id))
            elif server_key(engine_id):
                choices.append((API_ENGINES[engine_id]["label"], engine_id))
        elif local_status(engine_id)[0]:
            choices.append((LOCAL_ENGINES[engine_id]["label"], engine_id))
    return choices


def resolve(engine_id: str, settings: Optional[Dict] = None) -> Dict[str, object]:
    """Réglages à appliquer à src.config pour une question. Lève ValueError si
    le moteur n'est pas utilisable."""
    if engine_id in API_ENGINES:
        info = API_ENGINES[engine_id]
        entry = user_entry(engine_id, settings)
        key = entry["key"] or server_key(engine_id)
        if not key:
            raise ValueError(
                f"Aucune clé {info['provider']} disponible. Ajoutez la vôtre dans l'onglet Paramètres."
            )
        model = entry["model"] or default_model(engine_id)
        cfg = {name["key_name"]: "" for name in API_ENGINES.values()}
        cfg.update({
            "LLM_BACKEND": engine_id,
            info["key_name"]: key,
            "MODEL_EXTRACTOR_PATH": model,
            "MODEL_REASONER_PATH": model,
        })
        return cfg
    if engine_id in LOCAL_ENGINES:
        ok, reason = local_status(engine_id)
        if not ok:
            raise ValueError(reason)
        cfg = {"LLM_BACKEND": "default"}
        if engine_id == "lite_version":
            lite = _config_value("LITE_MODEL_PATH")
            cfg.update({"MODEL_EXTRACTOR_PATH": lite, "MODEL_REASONER_PATH": lite})
        else:
            cfg.update({
                "MODEL_EXTRACTOR_PATH": _config_value("MODEL_EXTRACTOR_PATH"),
                "MODEL_REASONER_PATH": _config_value("MODEL_REASONER_PATH"),
            })
        return cfg
    raise ValueError(f"Moteur inconnu : {engine_id}")


def display_name(engine_id: str) -> str:
    if engine_id in API_ENGINES:
        return API_ENGINES[engine_id]["label"]
    if engine_id in LOCAL_ENGINES:
        return LOCAL_ENGINES[engine_id]["label"]
    return engine_id
