import json
import logging
import os
import re
import gc
import sys
from contextlib import contextmanager
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from src.config import (
    JSON_GENERATION_MAX_RETRIES,
    JSON_GENERATION_MAX_TOKEN_MULTIPLIER,
    VLLM_GPU_MEMORY_UTILIZATION,
    VLLM_MAX_NUM_BATCHED_TOKENS,
)

LOGGER = logging.getLogger(__name__)

# Marge ajoutée à max_output_tokens pour la réflexion interne des modèles Gemini.
GEMINI_THINKING_HEADROOM_TOKENS = 8192
# Délai maximum d'un appel Gemini, et modèles de repli en cas de surcharge.
GEMINI_TIMEOUT_MS = 120_000
GEMINI_FALLBACK_MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash"]


class JSONGenerationError(RuntimeError):
    """Expose failed JSON generation details to the optional HTML diagnostic."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        attempts: int,
        raw_response: Optional[str] = None,
        cause: Optional[BaseException] = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.attempts = attempts
        self.raw_response = raw_response
        self.cause_type = type(cause).__name__ if cause is not None else None
        self.cause_message = str(cause) if cause is not None else None


class ProviderFatalError(RuntimeError):
    """Erreur de fournisseur qu'il est inutile de réessayer (clé, quota, modèle).

    Le message est rédigé pour être affiché tel quel dans l'interface.
    """


def _status_code(exc: BaseException) -> Optional[int]:
    for attr in ("status_code", "code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _classify_provider_error(exc: BaseException) -> str:
    message = str(exc).lower()
    code = _status_code(exc)
    if (
        code in (401, 403)
        or "api key not valid" in message
        or "api_key_invalid" in message
        or "incorrect api key" in message
        or "invalid x-api-key" in message
        or "invalid api key" in message
    ):
        return "auth"
    if "credit balance" in message or "insufficient_quota" in message or "billing" in message:
        return "billing"
    if code == 404:
        return "not_found"
    if code == 429 or "resource_exhausted" in message or "rate limit" in message or "rate_limit" in message:
        if "perday" in message or "per day" in message or "per_day" in message:
            return "daily_quota"
        return "transient"
    if code in (500, 502, 503, 504, 529) or any(
        marker in message
        for marker in ("overloaded", "unavailable", "timed out", "timeout", "connection error", "temporarily")
    ):
        return "transient"
    return "other"


def _retry_delay_seconds(exc: BaseException, attempt: int) -> float:
    message = str(exc)
    match = re.search(r"retry in ([0-9.]+)\s*s", message, flags=re.IGNORECASE) or re.search(
        r"retryDelay['\"]?\s*[:=]\s*['\"]?([0-9.]+)s", message
    )
    if match:
        try:
            return min(65.0, max(2.0, float(match.group(1)) + 1.0))
        except ValueError:
            pass
    return float(min(60, 5 * (2 ** attempt)))


PROVIDER_MAX_ATTEMPTS = 5


def _check_cancelled() -> None:
    """Arrête la recherche si la page qui l'a lancée a été fermée."""
    try:
        from src import job_queue
    except Exception:
        return
    try:
        job_queue.check_cancelled()
    except job_queue.SearchCancelled as exc:
        raise ProviderFatalError(str(exc)) from exc


def _set_note(note: str) -> None:
    try:
        from src import job_queue

        job_queue.set_note(note)
    except Exception:
        pass


def call_provider(provider: str, request, on_transient=None):
    """Appelle l'API d'un fournisseur en réessayant les erreurs passagères.

    Limites par minute, surcharge et coupures réseau sont réessayées avec une
    attente croissante, affichée dans la jauge. Clé refusée, quota journalier
    épuisé ou modèle inconnu lèvent directement une ProviderFatalError avec un
    message clair. on_transient(attempt, exc) permet au fournisseur de réagir
    à une surcharge (par exemple changer de modèle) et renvoie un texte à afficher.
    """
    import time

    for attempt in range(PROVIDER_MAX_ATTEMPTS):
        _check_cancelled()
        try:
            result = request()
            _set_note("")
            return result
        except ProviderFatalError:
            raise
        except Exception as exc:
            kind = _classify_provider_error(exc)
            if kind == "auth":
                raise ProviderFatalError(
                    f"Clé API {provider} refusée. Vérifiez qu'elle est complète, sans espace, et toujours active."
                ) from exc
            if kind == "billing":
                raise ProviderFatalError(
                    f"Le compte {provider} n'a pas de crédit ou de facturation active pour cette clé."
                ) from exc
            if kind == "not_found":
                raise ProviderFatalError(
                    f"Modèle {provider} introuvable. Vérifiez le nom exact du modèle dans l'onglet Paramètres."
                ) from exc
            if kind == "daily_quota":
                raise ProviderFatalError(
                    f"Quota journalier {provider} atteint pour ce modèle. Réessayez demain, "
                    "ou choisissez un autre modèle dans l'onglet Paramètres."
                ) from exc
            if kind == "transient" and attempt < PROVIDER_MAX_ATTEMPTS - 1:
                delay = _retry_delay_seconds(exc, attempt)
                switched = on_transient(attempt, exc) if on_transient else ""
                note = switched or f"{provider} est surchargé ou limite les requêtes : nouvel essai dans {delay:.0f} s."
                LOGGER.warning("%s (tentative %s/%s) : %s", note, attempt + 1, PROVIDER_MAX_ATTEMPTS, exc)
                _set_note(note)
                if switched:
                    continue  # nouveau modèle : on réessaie tout de suite
                # Attente découpée pour pouvoir s'arrêter si la page est fermée.
                end = time.time() + delay
                while time.time() < end:
                    _check_cancelled()
                    time.sleep(min(2.0, max(0.0, end - time.time())))
                continue
            _set_note("")
            if kind == "transient":
                raise ProviderFatalError(
                    f"{provider} est surchargé en ce moment. Réessayez dans quelques minutes, "
                    "ou choisissez un autre moteur ou un autre modèle dans l'onglet Paramètres."
                ) from exc
            raise


@contextmanager
def _stdio_with_fileno_for_vllm():
    """Colab/IPython stdout has no fileno(), but vLLM V1 expects one."""
    def has_fileno(stream) -> bool:
        try:
            stream.fileno()
            return True
        except Exception:
            return False

    if has_fileno(sys.stdout) and has_fileno(sys.stderr):
        yield
        return

    old_stdout, old_stderr = sys.stdout, sys.stderr
    stdout = os.fdopen(os.dup(1), "w", buffering=1)
    stderr = os.fdopen(os.dup(2), "w", buffering=1)
    try:
        sys.stdout = stdout
        sys.stderr = stderr
        yield
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        stdout.close()
        stderr.close()


def _extract_json_object(raw: str) -> Dict:
    text = (raw or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if fenced:
        try:
            return _extract_json_object(fenced.group(1))
        except json.JSONDecodeError:
            pass

    decoder = json.JSONDecoder()
    best = None
    best_end = -1
    last_error: Optional[json.JSONDecodeError] = None
    for match in re.finditer(r"\{", text):
        try:
            candidate, end = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(candidate, dict):
            absolute_end = match.start() + end
            if absolute_end > best_end:
                best = candidate
                best_end = absolute_end
    if best is not None:
        return best
    if last_error is not None:
        raise last_error
    return json.loads(text)


class LLMBackend(ABC):
    @abstractmethod
    def generate_json(
        self,
        messages: List[Dict[str, str]],
        schema: Dict,
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ) -> Dict:
        pass

    @abstractmethod
    def generate_text(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ) -> str:
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        pass

    @abstractmethod
    def get_tokenizer(self):
        pass

    def close(self) -> None:
        pass


class CustomBackend(LLMBackend):
    def __init__(self, model_path: str, num_gpus: int = 1, max_model_len: int = 1024):
        import torch
        from transformers import AutoTokenizer
        from vllm import LLM

        if torch.cuda.device_count() == 0:
            tensor_parallel_size = 1
        else:
            tensor_parallel_size = min(num_gpus, torch.cuda.device_count())

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            cache_dir=model_path,
            local_files_only=True,
            trust_remote_code=True,
        )
        # bfloat16 n'existe qu'à partir des GPU Ampere (A100, L4…). Un T4 de Colab
        # gratuit doit passer en float16, sinon vLLM refuse de démarrer.
        supports_bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 8
        if "awq" in model_path.lower() or not supports_bf16:
            model_dtype = "float16"
        else:
            model_dtype = "bfloat16"
        max_num_batched_tokens = (
            int(VLLM_MAX_NUM_BATCHED_TOKENS)
            if VLLM_MAX_NUM_BATCHED_TOKENS is not None
            else min(4096, max_model_len)
        )
        with _stdio_with_fileno_for_vllm():
            self.model = LLM(
                model=model_path,
                tensor_parallel_size=tensor_parallel_size,
                max_model_len=max_model_len,
                max_num_batched_tokens=max_num_batched_tokens,
                max_num_seqs=1,
                gpu_memory_utilization=float(VLLM_GPU_MEMORY_UTILIZATION),
                swap_space=0,
                dtype=model_dtype,
                disable_custom_all_reduce=True,
            )

    def generate_json(
        self,
        messages: List[Dict[str, str]],
        schema: Dict,
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ) -> Dict:
        from vllm import SamplingParams
        from vllm.sampling_params import StructuredOutputsParams

        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        current_max_tokens = max(64, int(max_tokens))
        token_limit = max(current_max_tokens, int(max_tokens) * int(JSON_GENERATION_MAX_TOKEN_MULTIPLIER))
        attempt_idx = 0
        last_error = None
        while attempt_idx < int(JSON_GENERATION_MAX_RETRIES):
            attempt_idx += 1
            sampling = SamplingParams(
                temperature=temperature,
                top_p=top_p,
                max_tokens=min(current_max_tokens, token_limit),
                structured_outputs=StructuredOutputsParams(
                    json=schema,
                    disable_additional_properties=True,
                ),
            )
            output = self.model.generate(prompt, sampling)[0].outputs[0].text.strip()
            try:
                return _extract_json_object(output)
            except json.JSONDecodeError as exc:
                last_error = exc
                LOGGER.error(
                    "JSON parsing failed in CustomBackend.generate_json (attempt %s, max_tokens=%s): %s at line=%s col=%s pos=%s",
                    attempt_idx,
                    min(current_max_tokens, token_limit),
                    exc.msg,
                    exc.lineno,
                    exc.colno,
                    exc.pos,
                )
                LOGGER.error("---- RAW_MODEL_OUTPUT_ATTEMPT_%s_START ----", attempt_idx)
                LOGGER.error(output)
                LOGGER.error("---- RAW_MODEL_OUTPUT_ATTEMPT_%s_END ----", attempt_idx)
                current_max_tokens = min(
                    token_limit,
                    max(current_max_tokens + 1, int(current_max_tokens * 1.5)),
                )
        raise RuntimeError(
            "Model did not return valid JSON after "
            f"{JSON_GENERATION_MAX_RETRIES} attempts; last error: {last_error}"
        )

    def generate_text(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ) -> str:
        from vllm import SamplingParams

        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        sampling = SamplingParams(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max(16, int(max_tokens)),
        )
        return self.model.generate(prompt, sampling)[0].outputs[0].text.strip()

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text or "", add_special_tokens=False))

    def get_tokenizer(self):
        return self.tokenizer

    def close(self) -> None:
        try:
            engine = getattr(self.model, "llm_engine", None)
            if engine is not None:
                executor = getattr(engine, "model_executor", None)
                if executor is not None and hasattr(executor, "shutdown"):
                    executor.shutdown()
                if hasattr(engine, "shutdown"):
                    engine.shutdown()
        except Exception as exc:
            LOGGER.warning("vLLM engine shutdown raised: %s", exc)
        try:
            del self.model
        except AttributeError:
            pass
        try:
            import torch

            if torch.distributed.is_available() and torch.distributed.is_initialized():
                torch.distributed.destroy_process_group()
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        except Exception as exc:
            LOGGER.warning("CUDA cleanup raised: %s", exc)
        try:
            from vllm.distributed.parallel_state import destroy_distributed_environment, destroy_model_parallel

            destroy_model_parallel()
            destroy_distributed_environment()
        except Exception:
            pass
        gc.collect()


class GeminiBackend(LLMBackend):
    def __init__(self, model_name: str, api_key: Optional[str] = None):
        from google import genai

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY is required when LLM_BACKEND='gemini_api'.")
        self.model_name = model_name
        # Délai maximum par appel (en millisecondes) : un appel ne peut plus rester
        # bloqué indéfiniment et empêcher les recherches suivantes.
        self.client = genai.Client(api_key=key, http_options={"timeout": GEMINI_TIMEOUT_MS})
        self._fallbacks = [m for m in GEMINI_FALLBACK_MODELS if m != model_name]

    @staticmethod
    def _extract_json(raw: str) -> Dict:
        return _extract_json_object(raw)

    @staticmethod
    def _messages_to_parts(messages: List[Dict[str, str]]) -> Dict[str, str]:
        system_parts: List[str] = []
        user_parts: List[str] = []
        assistant_parts: List[str] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            elif role == "assistant":
                assistant_parts.append(content)
            else:
                user_parts.append(content)
        if assistant_parts:
            user_parts.append("\n\nPrevious assistant context:\n" + "\n\n".join(assistant_parts))
        return {
            "system": "\n\n".join([p for p in system_parts if p.strip()]),
            "user": "\n\n".join([p for p in user_parts if p.strip()]),
        }

    def _generate_raw(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        top_p: float,
        response_schema: Optional[Dict] = None,
    ) -> str:
        parts = self._messages_to_parts(messages)
        # Sur les modèles Gemini récents, la réflexion interne est décomptée de
        # max_output_tokens : sans marge, la réponse JSON arrive vide ou tronquée.
        config = {
            "max_output_tokens": int(max(16, max_tokens)) + GEMINI_THINKING_HEADROOM_TOKENS,
        }
        # Google déconseille de modifier temperature/top_p à partir de Gemini 3.
        if not self.model_name.lower().startswith("gemini-3"):
            config["temperature"] = float(temperature)
            config["top_p"] = float(top_p)
        if parts["system"]:
            config["system_instruction"] = parts["system"]
        if response_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = response_schema

        def request():
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=parts["user"],
                config=config,
            )
            text = getattr(response, "text", None)
            if not text:
                raise RuntimeError("Gemini SDK returned an empty text response.")
            return text.strip()

        def on_transient(attempt, exc):
            # Après deux échecs dus à la surcharge, on bascule sur un autre modèle Gemini.
            message = str(exc).lower()
            overloaded = "503" in message or "unavailable" in message or "high demand" in message
            if overloaded and attempt >= 1 and self._fallbacks:
                previous, self.model_name = self.model_name, self._fallbacks.pop(0)
                return f"{previous} est saturé chez Google : bascule automatique sur {self.model_name}."
            return ""

        return call_provider("Gemini", request, on_transient)

    def generate_json(
        self,
        messages: List[Dict[str, str]],
        schema: Dict,
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ) -> Dict:
        current_max_tokens = max(64, int(max_tokens))
        token_limit = max(
            current_max_tokens,
            int(max_tokens) * int(JSON_GENERATION_MAX_TOKEN_MULTIPLIER),
        )
        attempt_idx = 0
        last_error = None
        last_raw = None
        while attempt_idx < int(JSON_GENERATION_MAX_RETRIES):
            attempt_idx += 1
            try:
                raw = self._generate_raw(
                    messages,
                    max_tokens=min(current_max_tokens, token_limit),
                    temperature=temperature,
                    top_p=top_p,
                    response_schema=schema,
                )
                last_raw = raw
            except ProviderFatalError:
                raise
            except Exception as exc:
                raise JSONGenerationError(
                    f"Gemini request failed during JSON generation: {exc}",
                    provider="Gemini",
                    attempts=attempt_idx,
                    cause=exc,
                ) from exc
            try:
                return self._extract_json(raw)
            except json.JSONDecodeError as exc:
                last_error = exc
                LOGGER.error(
                    "JSON parsing failed in GeminiBackend.generate_json (attempt %s, max_tokens=%s): %s at line=%s col=%s pos=%s",
                    attempt_idx,
                    min(current_max_tokens, token_limit),
                    exc.msg,
                    exc.lineno,
                    exc.colno,
                    exc.pos,
                )
                LOGGER.error("---- RAW_GEMINI_OUTPUT_ATTEMPT_%s_START ----", attempt_idx)
                LOGGER.error(raw)
                LOGGER.error("---- RAW_GEMINI_OUTPUT_ATTEMPT_%s_END ----", attempt_idx)
                current_max_tokens = min(
                    token_limit,
                    max(current_max_tokens + 1, int(current_max_tokens * 1.5)),
                )
        raise JSONGenerationError(
            "Gemini did not return valid JSON after "
            f"{JSON_GENERATION_MAX_RETRIES} attempts; last error: {last_error}",
            provider="Gemini",
            attempts=attempt_idx,
            raw_response=last_raw,
            cause=last_error,
        )

    def generate_text(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ) -> str:
        return self._generate_raw(messages, max_tokens=max_tokens, temperature=temperature, top_p=top_p)

    def count_tokens(self, text: str) -> int:
        return max(1, int(len(text or "") / 4))

    def get_tokenizer(self):
        return None

    def close(self) -> None:
        self.client.close()


class OpenAIBackend(LLMBackend):
    def __init__(self, model_name: str, api_key: Optional[str] = None):
        from openai import OpenAI

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY is required when LLM_BACKEND='openai_api'.")
        self.model_name = model_name
        self.client = OpenAI(api_key=key, timeout=180.0)

    def _generate_raw(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        top_p: float,
        response_format: Optional[Dict] = None,
    ) -> str:
        params = {
            "model": self.model_name,
            "messages": messages,
            "temperature": float(temperature),
            "top_p": float(top_p),
            # max_completion_tokens remplace max_tokens et fonctionne avec tous les modèles actuels.
            "max_completion_tokens": int(max(16, max_tokens)),
        }
        if response_format:
            params["response_format"] = response_format

        def request():
            try:
                completion = self.client.chat.completions.create(**params)
            except Exception as exc:
                # Les modèles de raisonnement (o-series, gpt-5…) refusent temperature/top_p.
                message = str(exc).lower()
                if _status_code(exc) == 400 and ("temperature" in message or "top_p" in message):
                    params.pop("temperature", None)
                    params.pop("top_p", None)
                    completion = self.client.chat.completions.create(**params)
                else:
                    raise
            content = completion.choices[0].message.content
            if not content:
                raise RuntimeError("OpenAI SDK returned an empty text response.")
            return content.strip()

        return call_provider("OpenAI", request)

    def generate_json(
        self,
        messages: List[Dict[str, str]],
        schema: Dict,
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ) -> Dict:
        schema_note = {
            "role": "system",
            "content": (
                "Return valid JSON only. Do not use markdown fences.\n"
                "Follow this JSON Schema exactly:\n"
                f"{json.dumps(schema, ensure_ascii=False)}"
            ),
        }
        current_max_tokens = max(64, int(max_tokens))
        token_limit = max(
            current_max_tokens,
            int(max_tokens) * int(JSON_GENERATION_MAX_TOKEN_MULTIPLIER),
        )
        attempt_idx = 0
        last_error = None
        last_raw = None
        while attempt_idx < int(JSON_GENERATION_MAX_RETRIES):
            attempt_idx += 1
            try:
                raw = self._generate_raw(
                    messages + [schema_note],
                    max_tokens=min(current_max_tokens, token_limit),
                    temperature=temperature,
                    top_p=top_p,
                    response_format={"type": "json_object"},
                )
                last_raw = raw
            except ProviderFatalError:
                raise
            except Exception as exc:
                raise JSONGenerationError(
                    f"OpenAI request failed during JSON generation: {exc}",
                    provider="OpenAI",
                    attempts=attempt_idx,
                    cause=exc,
                ) from exc
            try:
                return _extract_json_object(raw)
            except json.JSONDecodeError as exc:
                last_error = exc
                LOGGER.error(
                    "JSON parsing failed in OpenAIBackend.generate_json (attempt %s, max_tokens=%s): %s at line=%s col=%s pos=%s",
                    attempt_idx,
                    min(current_max_tokens, token_limit),
                    exc.msg,
                    exc.lineno,
                    exc.colno,
                    exc.pos,
                )
                LOGGER.error("---- RAW_OPENAI_OUTPUT_ATTEMPT_%s_START ----", attempt_idx)
                LOGGER.error(raw)
                LOGGER.error("---- RAW_OPENAI_OUTPUT_ATTEMPT_%s_END ----", attempt_idx)
                current_max_tokens = min(
                    token_limit,
                    max(current_max_tokens + 1, int(current_max_tokens * 1.5)),
                )
        raise JSONGenerationError(
            "OpenAI did not return valid JSON after "
            f"{JSON_GENERATION_MAX_RETRIES} attempts; last error: {last_error}",
            provider="OpenAI",
            attempts=attempt_idx,
            raw_response=last_raw,
            cause=last_error,
        )

    def generate_text(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ) -> str:
        return self._generate_raw(messages, max_tokens=max_tokens, temperature=temperature, top_p=top_p)

    def count_tokens(self, text: str) -> int:
        return max(1, int(len(text or "") / 4))

    def get_tokenizer(self):
        return None

    def close(self) -> None:
        self.client.close()


class AnthropicBackend(LLMBackend):
    def __init__(self, model_name: str, api_key: Optional[str] = None):
        from anthropic import Anthropic

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_BACKEND='anthropic_api'.")
        self.model_name = model_name
        self.client = Anthropic(api_key=key, timeout=180.0)

    @staticmethod
    def _split_messages(messages: List[Dict[str, str]]) -> Dict[str, object]:
        system_parts = []
        chat_messages = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            elif role == "assistant":
                chat_messages.append({"role": "assistant", "content": content})
            else:
                chat_messages.append({"role": "user", "content": content})
        return {
            "system": "\n\n".join([p for p in system_parts if p.strip()]),
            "messages": chat_messages,
        }

    def _generate_raw(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> str:
        parts = self._split_messages(messages)
        # Les modèles Claude récents refusent temperature et top_p ensemble :
        # seule la température est transmise.
        params = {
            "model": self.model_name,
            "messages": parts["messages"],
            "max_tokens": int(max(16, max_tokens)),
            "temperature": float(temperature),
        }
        if parts["system"]:
            params["system"] = parts["system"]

        def request():
            message = self.client.messages.create(**params)
            text = "".join(
                block.text
                for block in message.content
                if getattr(block, "type", None) == "text"
            ).strip()
            if not text:
                raise RuntimeError("Anthropic SDK returned an empty text response.")
            return text

        return call_provider("Anthropic", request)

    def generate_json(
        self,
        messages: List[Dict[str, str]],
        schema: Dict,
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ) -> Dict:
        schema_note = {
            "role": "system",
            "content": (
                "Return valid JSON only. Do not use markdown fences.\n"
                "Follow this JSON Schema exactly:\n"
                f"{json.dumps(schema, ensure_ascii=False)}"
            ),
        }
        current_max_tokens = max(64, int(max_tokens))
        token_limit = max(
            current_max_tokens,
            int(max_tokens) * int(JSON_GENERATION_MAX_TOKEN_MULTIPLIER),
        )
        attempt_idx = 0
        last_error = None
        last_raw = None
        while attempt_idx < int(JSON_GENERATION_MAX_RETRIES):
            attempt_idx += 1
            try:
                raw = self._generate_raw(
                    messages + [schema_note],
                    max_tokens=min(current_max_tokens, token_limit),
                    temperature=temperature,
                    top_p=top_p,
                )
                last_raw = raw
            except ProviderFatalError:
                raise
            except Exception as exc:
                raise JSONGenerationError(
                    f"Anthropic request failed during JSON generation: {exc}",
                    provider="Anthropic",
                    attempts=attempt_idx,
                    cause=exc,
                ) from exc
            try:
                return _extract_json_object(raw)
            except json.JSONDecodeError as exc:
                last_error = exc
                LOGGER.error(
                    "JSON parsing failed in AnthropicBackend.generate_json (attempt %s, max_tokens=%s): %s at line=%s col=%s pos=%s",
                    attempt_idx,
                    min(current_max_tokens, token_limit),
                    exc.msg,
                    exc.lineno,
                    exc.colno,
                    exc.pos,
                )
                LOGGER.error("---- RAW_ANTHROPIC_OUTPUT_ATTEMPT_%s_START ----", attempt_idx)
                LOGGER.error(raw)
                LOGGER.error("---- RAW_ANTHROPIC_OUTPUT_ATTEMPT_%s_END ----", attempt_idx)
                current_max_tokens = min(
                    token_limit,
                    max(current_max_tokens + 1, int(current_max_tokens * 1.5)),
                )
        raise JSONGenerationError(
            "Anthropic did not return valid JSON after "
            f"{JSON_GENERATION_MAX_RETRIES} attempts; last error: {last_error}",
            provider="Anthropic",
            attempts=attempt_idx,
            raw_response=last_raw,
            cause=last_error,
        )

    def generate_text(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ) -> str:
        return self._generate_raw(messages, max_tokens=max_tokens, temperature=temperature, top_p=top_p)

    def count_tokens(self, text: str) -> int:
        return max(1, int(len(text or "") / 4))

    def get_tokenizer(self):
        return None

    def close(self) -> None:
        self.client.close()
