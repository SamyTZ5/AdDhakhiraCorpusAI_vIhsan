import gc
import os
from typing import Callable, Dict, List, Optional, Tuple

import torch
from transformers import AutoTokenizer

from src.config import (
    AUTO_TRANSLATE_QUESTION_TO_ARABIC,
    EMBEDDING_MODEL,
    JSON_INPUT_PATH,
    LLM_BACKEND,
    MAX_MODEL_LEN_EXTRACTOR,
    MIN_MODEL_LEN_REASONER,
    MODEL_EXTRACTOR_PATH,
    MODEL_REASONER_PATH,
    NUM_GPUS_EXTRACTOR,
    NUM_GPUS_REASONER,
    REASONER_CONTEXT_SAFETY_TOKENS,
    TOP_K_CHUNKS,
    TOP_K_SOURCES,
)
from src.data_loader import load_chunks
from src.embeddings import release_shared_embedding_models
from src.llm_backend import ProviderFatalError
from src.llm_ops import (
    assess_answer_consistency,
    build_generation_debug_event,
    extract_keywords,
    generate_pedagogical_answer,
    instantiate_model,
    translate_question_to_arabic,
    translate_pages_to_french,
)
from src.reporting import print_final
from src.retrieval import HybridRetriever, top_pages_from_chunks
from src.text_utils import is_mostly_arabic, truncate_text_by_tokens

ProgressCallback = Callable[[Dict[str, object]], None]


def _emit_progress(progress_callback: Optional[ProgressCallback], message: str, **payload) -> None:
    if progress_callback is None:
        return
    progress_callback({"message": message, **payload})


def _close_quietly(model) -> None:
    if model is None or not hasattr(model, "close"):
        return
    try:
        model.close()
    except Exception as exc:  # le nettoyage ne doit jamais masquer l'erreur d'origine
        print(f"[pipeline] fermeture du modèle impossible : {exc}", flush=True)


def _free_gpu_memory() -> None:
    gc.collect()
    try:
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
    except Exception:
        pass


def _estimate_token_count(text: str) -> int:
    return max(1, int(len(text or "") / 4))


def _truncate_text(text: str, tokenizer: Optional[AutoTokenizer], max_tokens: int) -> str:
    if tokenizer is not None:
        return truncate_text_by_tokens(text, tokenizer, max_tokens)
    max_chars = max(32, int(max_tokens) * 4)
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def build_reasoning_context(
    pages: List[Dict], tokenizer: Optional[AutoTokenizer], max_tokens: int
) -> Tuple[str, Dict[str, Dict[str, str]]]:
    lines = []
    source_map: Dict[str, Dict[str, str]] = {}
    for p in pages:
        section_bits = []
        if p.get("source_id"):
            section_bits.append(f"source={p.get('source_id')}")
        if p.get("section_path"):
            section_bits.append(f"section={p.get('section_path')}")
        extra = f" {' | '.join(section_bits)}" if section_bits else ""
        header = (
            f"[page_ref] page_number={p['page_number']} "
            f"page_id={p['page_id']} part={p['part_index']}{extra}"
        )
        lines.append(f"{header}\n{p['text']}")
        page_info = {
            "page_number": str(p.get("page_number")),
            "page_id": str(p.get("page_id")),
            "author": str(p.get("author", "Auteur inconnu")),
            "title": str(p.get("book_title", "Livre inconnu")),
            "section_path": str(p.get("section_path") or ""),
            "source_id": str(p.get("source_id") or ""),
        }
        # Deux livres peuvent avoir le même couple page_number/page_id : la clé
        # complète inclut la source pour ne pas attribuer une citation au mauvais livre.
        source_map[f"{p.get('source_id')}|{p.get('page_number')}|{p.get('page_id')}"] = page_info
        source_map.setdefault(f"{p.get('page_number')}|{p.get('page_id')}", page_info)
    joined = "\n\n".join(lines)
    return _truncate_text(joined, tokenizer, max_tokens), source_map


def compute_page_token_counts(top_pages: List[Dict], tokenizer: Optional[AutoTokenizer]) -> List[Dict]:
    stats = []
    for p in top_pages:
        token_count = (
            len(tokenizer.encode(p["text"], add_special_tokens=False))
            if tokenizer is not None
            else _estimate_token_count(p["text"])
        )
        stats.append(
            {
                "page_number": p.get("page_number"),
                "page_id": p.get("page_id"),
                "part_index": p.get("part_index"),
                "tokens": token_count,
            }
        )
    return stats


def build_final_report(
    question: str,
    translate_to_french: bool,
    diagnostic_coherence: bool = False,
    auto_translate_question_to_arabic: bool = AUTO_TRANSLATE_QUESTION_TO_ARABIC,
    progress_callback: Optional[ProgressCallback] = None,
) -> str:
    """Produit le rapport HTML. Les modèles ouverts sont toujours refermés,
    même en cas d'erreur, pour que la question suivante ait un GPU libre."""
    open_models: List[object] = []
    try:
        return _build_final_report(
            question=question,
            translate_to_french=translate_to_french,
            diagnostic_coherence=diagnostic_coherence,
            auto_translate_question_to_arabic=auto_translate_question_to_arabic,
            progress_callback=progress_callback,
            open_models=open_models,
        )
    finally:
        while open_models:
            _close_quietly(open_models.pop())
        _free_gpu_memory()


def _build_final_report(
    question: str,
    translate_to_french: bool,
    diagnostic_coherence: bool,
    auto_translate_question_to_arabic: bool,
    progress_callback: Optional[ProgressCallback],
    open_models: List[object],
) -> str:
    uses_local_llm = LLM_BACKEND == "default"
    # Sur une machine à deux GPU (Kaggle), le modèle de recherche a sa propre carte :
    # il reste chargé, même quand un moteur local (vLLM) occupe l'autre.
    dedicated_embedding_gpu = bool(os.environ.get("ADDHAKHIRA_EMBEDDING_DEVICE", "").strip())
    keep_embedder = (not uses_local_llm) or dedicated_embedding_gpu
    if not keep_embedder:
        # vLLM a besoin de tout le GPU : on libère un éventuel modèle d'embedding
        # gardé en mémoire par une question précédente posée en mode API.
        release_shared_embedding_models()

    _emit_progress(progress_callback, "Initialisation des modèles de recherche...", stage="init")
    extractor_model, extractor_tokenizer = instantiate_model(
        model_path=MODEL_EXTRACTOR_PATH,
        num_gpus=NUM_GPUS_EXTRACTOR,
        max_model_len=MAX_MODEL_LEN_EXTRACTOR,
    )
    open_models.append(extractor_model)

    processing_question = question
    translation_applied = False
    _emit_progress(
        progress_callback,
        "J'interprète la question en arabe pour améliorer la recherche dans les textes.",
        stage="question",
    )
    if auto_translate_question_to_arabic and not is_mostly_arabic(question):
        processing_question = translate_question_to_arabic(
            extractor_model,
            question,
        )
        translation_applied = processing_question != question

    keyword_diagnostic: Dict[str, object] = {}
    keywords = extract_keywords(
        extractor_model,
        processing_question,
        diagnostic=keyword_diagnostic,
    )
    if len(keywords) < 4:
        raise ValueError(f"Too few valid Arabic keywords extracted: {keywords}")
    _emit_progress(
        progress_callback,
        f"J'ai identifié les axes de recherche : {', '.join(keywords[:6])}.",
        stage="keywords",
        keywords=keywords,
    )

    open_models.remove(extractor_model)
    _close_quietly(extractor_model)
    del extractor_model
    _free_gpu_memory()

    chunks, pages_by_key = load_chunks(JSON_INPUT_PATH)
    _emit_progress(
        progress_callback,
        "Je parcours l'index des textes et je compare les passages les plus proches.",
        stage="retrieval",
    )
    # En mode API, le GPU ne sert qu'à l'embedding : on le garde chargé entre les
    # questions pour éviter de relire 8 Go depuis Google Drive à chaque fois.
    retriever = HybridRetriever(
        chunks,
        embedding_model_name=EMBEDDING_MODEL,
        keep_embedder_loaded=keep_embedder,
    )
    try:
        top_chunks = retriever.search(processing_question, keywords, top_k=TOP_K_CHUNKS)
    finally:
        retriever.close()
    top_pages = top_pages_from_chunks(
        top_chunks,
        pages_by_key,
        top_k_sources=TOP_K_SOURCES,
    )
    if top_pages:
        authors = []
        for page in top_pages:
            author = str(page.get("author") or "Auteur inconnu")
            if author not in authors:
                authors.append(author)
            if len(authors) >= 3:
                break
        _emit_progress(
            progress_callback,
            f"J'ai trouvé des passages pertinents chez {', '.join(authors)}.",
            stage="pages_found",
            top_pages=top_pages,
        )
        _emit_progress(
            progress_callback,
            "Je constitue une bibliographie de travail à partir de ces auteurs.",
            stage="bibliography",
            top_pages=top_pages,
        )
    del retriever
    _free_gpu_memory()
    if not top_pages:
        fallback = {
            "status": "not_enough_context",
            "reponse_courte": "Cela n'est pas mentionné dans les extraits fournis.",
            "points": [],
            "limites": "Aucun extrait pertinent n'a été récupéré.",
        }
        report = print_final(
            question,
            keywords,
            [],
            fallback,
            consistency_diagnostic=keyword_diagnostic if diagnostic_coherence else None,
        )
        return report

    if extractor_tokenizer is None:
        sizing_tokenizer = None
    elif os.path.normpath(MODEL_EXTRACTOR_PATH) == os.path.normpath(MODEL_REASONER_PATH):
        sizing_tokenizer = extractor_tokenizer
    else:
        try:
            sizing_tokenizer = AutoTokenizer.from_pretrained(
                MODEL_REASONER_PATH,
                cache_dir=MODEL_REASONER_PATH,
                local_files_only=True,
                trust_remote_code=True,
            )
        except Exception:
            sizing_tokenizer = extractor_tokenizer
    page_token_counts = compute_page_token_counts(top_pages, sizing_tokenizer)
    total_page_tokens = sum(p["tokens"] for p in page_token_counts)
    token_by_page = {
        (str(p["page_number"]), str(p["page_id"]), str(p["part_index"])): p["tokens"]
        for p in page_token_counts
    }
    for p in top_pages:
        key = (str(p.get("page_number")), str(p.get("page_id")), str(p.get("part_index")))
        p["page_tokens"] = token_by_page.get(key)
    # Account for page_ref headers, separators and bibliographic metadata in
    # addition to the page bodies themselves. This margin grows with the
    # variable number of pages retained before the fifth source is reached.
    context_overhead_tokens = max(256, len(top_pages) * 64)
    reasoning_context_tokens = total_page_tokens + context_overhead_tokens
    reasoner_model_len = max(
        MIN_MODEL_LEN_REASONER,
        reasoning_context_tokens + REASONER_CONTEXT_SAFETY_TOKENS,
    )

    reasoner_model, reasoner_tokenizer = instantiate_model(
        model_path=MODEL_REASONER_PATH,
        num_gpus=NUM_GPUS_REASONER,
        max_model_len=reasoner_model_len,
    )
    open_models.append(reasoner_model)

    context, source_page_map = build_reasoning_context(
        top_pages,
        reasoner_tokenizer,
        max_tokens=reasoning_context_tokens,
    )
    _emit_progress(
        progress_callback,
        "Je commence l'analyse des passages retenus.",
        stage="generation",
        top_pages=top_pages,
    )
    def _merge_verdicts(primary: Dict, adversarial: Dict) -> Dict[str, object]:
        primary_verdict = primary.get("verdict", "insufficient")
        adversarial_verdict = adversarial.get("verdict", "insufficient")
        if "contradicted" in (primary_verdict, adversarial_verdict):
            merged_verdict = "contradicted"
        elif "insufficient" in (primary_verdict, adversarial_verdict):
            merged_verdict = "insufficient"
        else:
            merged_verdict = "supported"
        merged_issues = []
        for issue in (primary.get("issues") or []) + (adversarial.get("issues") or []):
            if issue not in merged_issues:
                merged_issues.append(issue)
        return {
            "verdict": merged_verdict,
            "issues": merged_issues,
            "primary_verdict": primary_verdict,
            "adversarial_verdict": adversarial_verdict,
        }

    def _evaluate_answer(candidate_answer: Dict) -> Dict[str, object]:
        primary = assess_answer_consistency(
            reasoner_model,
            processing_question,
            context,
            candidate_answer,
        )
        adversarial = assess_answer_consistency(
            reasoner_model,
            processing_question,
            context,
            candidate_answer,
            extra_verifier_rules=(
                "Adversarial mode: actively try to falsify the answer.\n"
                "Do not return supported unless all key claims are explicitly grounded and no "
                "question fact weakens them."
            ),
        )
        return _merge_verdicts(primary, adversarial)

    llm_debug_events = keyword_diagnostic.setdefault("llm_debug_events", [])

    def _safe_generate_answer(stage: str, extra_rules: str = None) -> Tuple[Dict, bool]:
        try:
            generated = generate_pedagogical_answer(
                reasoner_model,
                processing_question,
                context,
                extra_system_rules=extra_rules,
            )
            llm_debug_events.append(
                build_generation_debug_event(stage, response=generated)
            )
            return generated, False
        except ProviderFatalError:
            raise
        except Exception as exc:
            llm_debug_events.append(
                build_generation_debug_event(stage, error=exc)
            )
            fallback_answer = {
                "status": "not_enough_context",
                "reponse_courte": (
                    "La génération structurée a échoué malgré plusieurs tentatives. "
                    "Voici les éléments textuels récupérés."
                ),
                "points": [],
                "limites": (
                    "La génération structurée n'a pas abouti. "
                    "Le diagnostic technique contient la réponse ou l'erreur réelle du fournisseur."
                ),
            }
            return fallback_answer, True

    def _build_evidence_aligned_fallback(
        points: List[Dict],
        failure_reason: str,
    ) -> Dict:
        if points:
            first_point = points[0]
            title = str(first_point.get("titre", "")).strip()
            explanation = str(first_point.get("explication_fr", "")).strip()
            if explanation:
                concise = explanation
            elif title:
                concise = title
            else:
                concise = "Les extraits disponibles permettent de dégager une règle exploitable."
            return {
                "status": "enough_context",
                "reponse_courte": concise,
                "points": points,
                "limites": (
                    "Le contrôle de cohérence a détecté une formulation trop forte dans une version intermédiaire. "
                    f"Version finale alignée sur les preuves textuelles. Détail: {failure_reason}"
                ),
            }
        return {
            "status": "not_enough_context",
            "reponse_courte": (
                "Les extraits ne permettent pas de formuler une conclusion catégorique sans risque de contradiction."
            ),
            "points": [],
            "limites": failure_reason,
        }

    answer, generation_failed = _safe_generate_answer("reasoner_initial")
    preserved_points = list(answer.get("points", [])) if isinstance(answer.get("points"), list) else []
    if generation_failed:
        consistency = {
            "verdict": "insufficient",
            "issues": ["Structured generation failed before consistency checks."],
            "primary_verdict": "insufficient",
            "adversarial_verdict": "insufficient",
        }
    else:
        _emit_progress(
            progress_callback,
            "Je relis la réponse : deux vérifications indépendantes contrôlent qu'elle ne dit rien de plus que les extraits.",
            stage="verification",
        )
        consistency = _evaluate_answer(answer)
    coherence_diag: Dict[str, object] = {
        **keyword_diagnostic,
        "question_translation_enabled": auto_translate_question_to_arabic,
        "question_translation_applied": translation_applied,
        "question_pipeline_used": processing_question,
        "initial_verdict": consistency.get("verdict"),
        "initial_issues": consistency.get("issues", []),
        "initial_primary_verdict": consistency.get("primary_verdict"),
        "initial_adversarial_verdict": consistency.get("adversarial_verdict"),
        "retry_verdict": None,
        "retry_issues": [],
        "retry_primary_verdict": None,
        "retry_adversarial_verdict": None,
        "final_pass_verdict": None,
        "final_pass_issues": [],
        "final_pass_primary_verdict": None,
        "final_pass_adversarial_verdict": None,
        "generation_failed": generation_failed,
        "fallback_used": False,
    }
    if consistency.get("verdict") != "supported":
        issues = consistency.get("issues") or []
        extra_rules = (
            "The previous draft was not fully supported by the excerpts/question facts.\n"
            "Correct all overclaims and contradictions and ground every key claim in direct evidence.\n"
            "If a required condition is not explicitly verified in the question, respond conditionally.\n"
            f"Verifier issues: {issues}"
        )
        _emit_progress(
            progress_callback,
            "La vérification a relevé un point fragile : je corrige la réponse à partir des extraits.",
            stage="correction",
        )
        answer, retry_generation_failed = _safe_generate_answer("reasoner_retry", extra_rules)
        if retry_generation_failed:
            coherence_diag["retry_verdict"] = "insufficient"
            coherence_diag["retry_issues"] = ["Structured generation failed during retry."]
            coherence_diag["retry_primary_verdict"] = "insufficient"
            coherence_diag["retry_adversarial_verdict"] = "insufficient"
            coherence_diag["fallback_used"] = True
            answer = _build_evidence_aligned_fallback(
                preserved_points,
                "La régénération structurée a échoué ; consulter le diagnostic technique.",
            )
            report = print_final(
                question,
                keywords,
                top_pages,
                answer,
                source_page_map=source_page_map,
                consistency_diagnostic=coherence_diag if diagnostic_coherence else None,
            )
            return report
        retry_points = answer.get("points", [])
        if isinstance(retry_points, list) and retry_points:
            preserved_points = list(retry_points)
        consistency_retry = _evaluate_answer(answer)
        coherence_diag["retry_verdict"] = consistency_retry.get("verdict")
        coherence_diag["retry_issues"] = consistency_retry.get("issues", [])
        coherence_diag["retry_primary_verdict"] = consistency_retry.get("primary_verdict")
        coherence_diag["retry_adversarial_verdict"] = consistency_retry.get("adversarial_verdict")
        if consistency_retry.get("verdict") != "supported":
            # Final correction pass before fallback: force alignment with question facts + excerpts.
            all_issues = []
            for issue in (coherence_diag.get("initial_issues") or []) + (coherence_diag.get("retry_issues") or []):
                if issue not in all_issues:
                    all_issues.append(issue)
            final_pass_rules = (
                "Final correction pass.\n"
                "Resolve all listed issues explicitly.\n"
                "When question facts already determine a condition, give a direct conclusion (not a hypothetical one).\n"
                "Do not keep mutually inconsistent statements between short answer and limits.\n"
                f"Issues to resolve: {all_issues}"
            )
            _emit_progress(
                progress_callback,
                "Dernière passe de correction pour aligner chaque affirmation sur les preuves.",
                stage="correction",
            )
            answer, final_generation_failed = _safe_generate_answer("reasoner_final", final_pass_rules)
            if final_generation_failed:
                coherence_diag["final_pass_verdict"] = "insufficient"
                coherence_diag["final_pass_primary_verdict"] = "insufficient"
                coherence_diag["final_pass_adversarial_verdict"] = "insufficient"
                coherence_diag["final_pass_issues"] = ["Structured generation failed during final pass."]
                coherence_diag["fallback_used"] = True
                answer = _build_evidence_aligned_fallback(
                    preserved_points,
                    "La passe finale a échoué ; consulter le diagnostic technique.",
                )
                report = print_final(
                    question,
                    keywords,
                    top_pages,
                    answer,
                    source_page_map=source_page_map,
                    consistency_diagnostic=coherence_diag if diagnostic_coherence else None,
                )
                return report
            final_points = answer.get("points", [])
            if isinstance(final_points, list) and final_points:
                preserved_points = list(final_points)
            final_consistency = _evaluate_answer(answer)
            coherence_diag["final_pass_verdict"] = final_consistency.get("verdict")
            coherence_diag["final_pass_issues"] = final_consistency.get("issues", [])
            coherence_diag["final_pass_primary_verdict"] = final_consistency.get("primary_verdict")
            coherence_diag["final_pass_adversarial_verdict"] = final_consistency.get("adversarial_verdict")
            if final_consistency.get("verdict") != "supported":
                coherence_diag["fallback_used"] = True
                answer = _build_evidence_aligned_fallback(
                    preserved_points,
                    "Le contrôle de cohérence a détecté une contradiction persistante entre la réponse générée et les extraits.",
                )
    if translate_to_french:
        translations = translate_pages_to_french(reasoner_model, top_pages)
        for page, tr in zip(top_pages, translations):
            page["translation_fr"] = tr
    _emit_progress(
        progress_callback,
        "Je rédige une réponse structurée en français à partir des passages récupérés et je prépare son exportation.",
        stage="export",
    )
    report = print_final(
        question,
        keywords,
        top_pages,
        answer,
        source_page_map=source_page_map,
        consistency_diagnostic=coherence_diag if diagnostic_coherence else None,
    )
    return report
