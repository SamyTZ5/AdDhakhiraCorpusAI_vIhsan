"""Contenus de l'interface : guide, fonctionnement technique, corpus, jauge.

Ce module ne contient que du HTML généré en Python, sans dépendance à
Gradio. Le notebook Colab et src/web_app.py l'utilisent tous les deux.
Les chiffres du corpus viennent de src/corpus_catalog.json, généré à
partir des fichiers de database/.
"""

import html as _html
import json
import math
from pathlib import Path
from typing import Dict, List, Optional

CATALOG_PATH = Path(__file__).with_name("corpus_catalog.json")


def _e(value) -> str:
    return _html.escape("" if value is None else str(value), quote=True)


def load_catalog() -> Dict:
    try:
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"book_count": 0, "total_pages": 0, "total_passages": 0, "books": []}


def _fmt_int(value: int) -> str:
    return f"{int(value):,}".replace(",", "\u202f")


# --------------------------------------------------------------------------
# Exemples de questions
# --------------------------------------------------------------------------

EXAMPLE_QUESTIONS = [
    "ما هي شروط صحة الصلاة؟",
    "Quelles sont les conditions de validité de la prière ?",
    "ما حكم قراءة الفاتحة للمأموم في الصلاة الجهرية؟",
    "Le voyageur peut-il essuyer sur ses chaussons (khuff) pour les ablutions ?",
    "ما حكم زكاة الحلي المستعمل؟",
]


# --------------------------------------------------------------------------
# Jauge d'avancement
# --------------------------------------------------------------------------

PROGRESS_STEPS = ["Préparation", "Question", "Recherche", "Rédaction", "Vérification", "Synthèse"]

# étape affichée, pourcentage de départ, pourcentage visé, durée typique (s)
_STAGE_PLAN = {
    "queued": (0, 1, 3, 60),
    "startup": (0, 2, 8, 15),
    "started": (0, 3, 8, 15),
    "init": (0, 8, 15, 15),
    "question": (1, 15, 20, 10),
    "keywords": (1, 20, 30, 10),
    "retrieval": (2, 30, 56, 90),
    "pages_found": (2, 56, 60, 5),
    "bibliography": (2, 60, 62, 5),
    "generation": (3, 62, 76, 30),
    "verification": (4, 76, 88, 25),
    "correction": (4, 80, 92, 30),
    "export": (5, 95, 99, 5),
    "done": (5, 100, 100, 1),
}


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    return f"{minutes} min {secs:02d} s" if minutes else f"{secs} s"


def progress_percent(stage: str, seconds_in_stage: float) -> float:
    """Avance vers le palier suivant sans jamais l'atteindre avant le vrai passage."""
    _, start, target, typical = _STAGE_PLAN.get(stage, _STAGE_PLAN["startup"])
    ratio = 1.0 - math.exp(-max(0.0, seconds_in_stage) / max(1.0, typical))
    return start + (target - start) * ratio


def progress_html(
    stage: str,
    message: str,
    *,
    state: str = "running",
    elapsed: float = 0.0,
    from_percent: float = 0.0,
    to_percent: float = 0.0,
    sources: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Jauge : étapes nommées, barre animée, message, durée et sources trouvées.

    state vaut "running", "done", "error" ou "idle".
    """
    if state == "idle":
        return (
            '<div class="ih-progress ih-progress-idle"><p class="ih-progress-msg">'
            f"{_e(message)}</p></div>"
        )
    step = _STAGE_PLAN.get(stage, _STAGE_PLAN["startup"])[0]
    if state == "done":
        step, from_percent, to_percent = len(PROGRESS_STEPS) - 1, 100.0, 100.0

    items = []
    for index, label in enumerate(PROGRESS_STEPS):
        if state == "done" or index < step:
            cls = "done"
        elif index == step:
            cls = "error" if state == "error" else "current"
        else:
            cls = "todo"
        items.append(f'<li class="{cls}"><span class="ih-step-mark"></span><span class="lbl">{_e(label)}</span></li>')

    source_html = ""
    if sources:
        seen, chips = set(), []
        for src in sources:
            title = str(src.get("title") or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            chips.append(
                f'<span class="ih-chip" lang="ar" dir="rtl" title="{_e(src.get("author"))}">{_e(title)}</span>'
            )
            if len(chips) >= 5:
                break
        if chips:
            source_html = f'<div class="ih-progress-sources"><span>Sources retenues</span>{"".join(chips)}</div>'

    hint = ""
    if state == "running" and step <= 2 and elapsed > 25:
        hint = (
            '<p class="ih-progress-hint">La première question est la plus longue : le modèle de recherche '
            "se charge depuis Google Drive. Les suivantes iront bien plus vite.</p>"
        )

    label = {
        "done": f"100 % · {_fmt_duration(elapsed)}",
        "error": "La recherche s'est arrêtée",
    }.get(state, f"{int(round(to_percent))} % · {_fmt_duration(elapsed)}")

    return f"""
<div class="ih-progress ih-progress-{state}" role="progressbar" aria-valuemin="0" aria-valuemax="100"
     aria-valuenow="{int(round(to_percent))}" aria-label="Avancement de la recherche">
  <ol class="ih-steps">{''.join(items)}</ol>
  <div class="ih-bar"><div class="ih-bar-fill" style="--from:{from_percent:.1f}%;--to:{to_percent:.1f}%"></div></div>
  <div class="ih-progress-meta"><p class="ih-progress-msg">{_e(message)}</p><span class="ih-progress-time">{_e(label)}</span></div>
  {source_html}
  {hint}
</div>
"""


class ProgressTracker:
    """Transforme le flux (message, étape) du pipeline en jauge animée."""

    def __init__(self):
        import time

        self._time = time.time
        self.started_at = self._time()
        self.stage = "startup"
        self.stage_started_at = self.started_at
        self.shown = 0.0

    def render(self, message: str, stage: Optional[str], sources=None, state: str = "running") -> str:
        now = self._time()
        if stage and stage != self.stage:
            self.stage = stage
            self.stage_started_at = now
        # Palier visé pendant les ~8 s qui séparent deux mises à jour.
        target = progress_percent(self.stage, now - self.stage_started_at + 8)
        target = max(target, self.shown)
        html = progress_html(
            self.stage,
            message,
            state=state,
            elapsed=now - self.started_at,
            from_percent=self.shown,
            to_percent=target,
            sources=sources,
        )
        self.shown = target
        return html


def idle_progress_html() -> str:
    return progress_html("startup", "Choisissez un moteur, écrivez votre question, puis lancez la recherche.", state="idle")


# --------------------------------------------------------------------------
# Page « Guide » (pour tous)
# --------------------------------------------------------------------------

def guide_html() -> str:
    cat = load_catalog()
    books = cat.get("book_count") or 18
    return f"""
<article class="ih-doc">
  <p class="ih-doc-lead">Ad-Dhakhira est un assistant de <strong>recherche bibliographique</strong> dans le fiqh
  mālikite. Vous posez une question ; il retrouve les passages qui en parlent dans {books} ouvrages de référence
  de l'école, puis rédige une synthèse où chaque affirmation renvoie à une citation arabe et à sa page.</p>

  <h3>Ce que fait l'assistant</h3>
  <p>Il fonctionne comme un étudiant méthodique à la bibliothèque. Il reformule d'abord votre question en
  termes de fiqh arabes, cherche les pages les plus proches dans les livres, les lit, puis rédige une réponse
  en français appuyée uniquement sur ce qu'il a lu. Une seconde lecture vérifie ensuite que la réponse ne dit
  rien que les extraits ne disent pas.</p>

  <h3>Bien poser sa question</h3>
  <ul>
    <li><strong>Une question, un sujet.</strong> « Quelles sont les conditions de validité de la prière ? »
    donne de meilleurs résultats que plusieurs questions mêlées.</li>
    <li><strong>L'arabe aide.</strong> Les livres sont en arabe : une question posée en arabe, ou qui contient
    les termes techniques (<bdi lang="ar">المسح على الخفين</bdi>, <bdi lang="ar">الزكاة</bdi>…), retrouve
    souvent des passages plus précis. Le français fonctionne aussi.</li>
    <li><strong>Donnez les faits utiles.</strong> Si la réponse dépend d'une situation (voyage, oubli, ordre des
    actes), précisez-la : l'assistant en tient compte et répond au conditionnel quand un élément manque.</li>
  </ul>

  <h3>Lire la synthèse</h3>
  <dl class="ih-dl">
    <dt>Avis synthétique</dt><dd>La réponse courte, formulée à partir des extraits.</dd>
    <dt>Preuves textuelles</dt><dd>Chaque point avec sa citation arabe, son explication et sa référence :
    livre, auteur, page.</dd>
    <dt>Limites</dt><dd>Ce que les extraits ne permettent pas d'affirmer. À lire avant de conclure.</dd>
    <dt>Pages consultées</dt><dd>Le texte arabe intégral des pages lues, pour vérifier soi-même.</dd>
    <dt>Diagnostic</dt><dd>Le détail technique des vérifications, utile en cas de doute ou d'erreur.</dd>
  </dl>

  <h3>Ce que l'outil ne fait pas</h3>
  <ul>
    <li><strong>Il ne délivre pas de fatwa.</strong> Il aide à retrouver et à lire les sources ; l'avis sur
    une situation personnelle reste l'affaire d'un savant qualifié.</li>
    <li><strong>Il ne connaît que son corpus.</strong> {books} livres, c'est beaucoup, mais pas toute l'école :
    l'absence d'un passage ne prouve pas l'absence d'un avis.</li>
    <li><strong>Il peut se tromper.</strong> Une citation peut être mal rattachée ou mal comprise. Vérifiez
    toujours la page citée dans l'onglet « Pages consultées », et idéalement dans l'édition imprimée.</li>
  </ul>

  <h3>Durée et confidentialité</h3>
  <p>Une recherche prend en général de une à quelques minutes ; la première de la session est la plus longue.
  Avec un moteur en ligne (Gemini, ChatGPT, Claude), la question et les extraits sont envoyés à ce fournisseur.
  Avec une clé Gemini gratuite, Google peut utiliser ces échanges pour améliorer ses modèles : n'écrivez pas
  d'informations personnelles dans vos questions.</p>
</article>
"""


# --------------------------------------------------------------------------
# Page « Sous le capot » (technique)
# --------------------------------------------------------------------------

def technical_html(project_url: str) -> str:
    cat = load_catalog()
    passages = _fmt_int(cat.get("total_passages") or 0)
    pages = _fmt_int(cat.get("total_pages") or 0)
    books = cat.get("book_count") or 0
    return f"""
<article class="ih-doc">
  <p class="ih-doc-lead">Une chaîne RAG (<em>retrieval-augmented generation</em>) en six étapes. Deux appels de
  modèle de langage encadrent une recherche vectorielle exacte, puis une double vérification contrôle la
  fidélité de la réponse aux extraits.</p>

  <h3>La chaîne de traitement</h3>
  <ol class="ih-pipeline">
    <li><strong>Mots-clés.</strong> Le modèle « extracteur » produit au moins 10 mots-clés arabes au format JSON
    imposé par un schéma (3 tentatives, puis repli sur les mots de la question). Traduction de la question vers
    l'arabe en option (<code>AUTO_TRANSLATE_QUESTION_TO_ARABIC</code>).</li>
    <li><strong>Recherche.</strong> La question est encodée par <code>Qwen3-Embedding-4B</code> (avec son
    instruction de requête), puis comparée par produit scalaire sur vecteurs normalisés, soit une similarité
    cosinus, à {passages} passages dans un index FAISS <code>IndexFlatIP</code> : recherche exacte, sans
    approximation. Les 40 passages les plus proches sont retenus.</li>
    <li><strong>Pages.</strong> Les passages sont regroupés par page (score = 0,75 × meilleur passage + 0,25 ×
    moyenne des trois meilleurs). Les pages sont prises par score décroissant jusqu'à couvrir 5 livres
    distincts ; les pages éditoriales (copyright, éditeur) sont écartées.</li>
    <li><strong>Rédaction.</strong> Le modèle « raisonneur » reçoit les pages entières, chacune précédée d'un
    en-tête <code>[page_ref]</code> (page, page_id, livre, section). Il répond en JSON contraint : statut,
    réponse courte, jusqu'à 5 points (titre, citation arabe verbatim, explication, référence) et limites.
    Température 0,2.</li>
    <li><strong>Vérification.</strong> Deux vérificateurs indépendants (standard et « adversarial », qui cherche
    à réfuter) rendent un verdict : <em>supported</em>, <em>contradicted</em> ou <em>insufficient</em>. Hors
    <em>supported</em>, la réponse est régénérée avec les problèmes relevés, puis une passe finale est tentée ;
    en dernier recours, une réponse prudente est reconstruite à partir des seules preuves.</li>
    <li><strong>Rapport.</strong> Les références sont résolues vers le livre, l'auteur et la page (clé
    livre + page + page_id, car un même numéro de page existe dans plusieurs livres), puis mises en forme
    dans une page HTML autonome, téléchargeable, avec l'onglet de diagnostic.</li>
  </ol>

  <h3>Modèles selon le moteur</h3>
  <div class="ih-table-wrap"><table class="ih-table">
    <thead><tr><th>Moteur</th><th>Extraction et rédaction</th><th>Recherche</th><th>Matériel</th></tr></thead>
    <tbody>
      <tr><td>Modèles locaux</td><td>gemma-4-12B-it, puis Qwen3.6-35B-A3B (vLLM)</td><td rowspan="5">Qwen3-Embedding-4B + FAISS</td><td>GPU de grande capacité</td></tr>
      <tr><td>Version légère</td><td>Qwen2.5-7B-Instruct-AWQ (vLLM)</td><td>GPU de 16 Go</td></tr>
      <tr><td>Gemini</td><td>gemini-3.5-flash-lite par défaut</td><td rowspan="3">GPU pour l'embedding seulement</td></tr>
      <tr><td>ChatGPT</td><td>gpt-4.1 par défaut</td></tr>
      <tr><td>Claude</td><td>claude-sonnet-5 par défaut</td></tr>
    </tbody>
  </table></div>
  <p>Les moteurs en ligne ne remplacent que les deux appels de langage : corpus, recherche, pages retenues et
  format du rapport sont identiques. Sur un T4 (Colab gratuit), l'embedding passe automatiquement en float16 et
  se charge directement sur le GPU.</p>

  <h3>Le corpus et son index</h3>
  <p>{books} livres, {pages} pages, découpées en {passages} passages de 1&nbsp;800 caractères avec
  250 caractères de recouvrement. Les pages éditoriales et les passages en double sont filtrés au chargement.
  L'index est signé (version, modèle d'embedding, empreinte SHA-256 de tous les passages, nombre de passages) :
  s'il ne correspond plus au corpus, il est refusé plutôt que de renvoyer de mauvaises pages. Un index
  préconstruit est téléchargé depuis Hugging Face pour éviter plusieurs heures d'encodage.</p>
  <p>Une recherche hybride est disponible (<code>ENABLE_HYBRID_RETRIEVAL</code>) : 0,6 × score lexical + 0,4 ×
  score dense, où le lexical combine BM25 (0,65), la fréquence des mots-clés (0,20) et les titres de section
  (0,15). Elle est désactivée par défaut.</p>

  <h3>Robustesse</h3>
  <ul>
    <li>Appels API réessayés avec attente croissante en cas de limite par minute ou de surcharge ; clé refusée,
    quota journalier ou modèle inconnu remontent un message explicite.</li>
    <li>Sorties JSON validées par schéma, avec relances et marge pour la réflexion interne des modèles Gemini.</li>
    <li>Modèles toujours libérés après une question, même en cas d'erreur ; en mode API, l'embedding reste
    chargé entre deux questions.</li>
    <li>Clés API masquées dans le diagnostic téléchargeable.</li>
  </ul>

  <h3>Réglages principaux</h3>
  <div class="ih-table-wrap"><table class="ih-table ih-table-compact">
    <tbody>
      <tr><td><code>TOP_K_CHUNKS</code></td><td>40</td><td>Passages retenus par la recherche</td></tr>
      <tr><td><code>TOP_K_SOURCES</code></td><td>5</td><td>Nombre de livres distincts dans le contexte</td></tr>
      <tr><td><code>REASONER_TEMPERATURE</code></td><td>0,2</td><td>Créativité de la rédaction</td></tr>
      <tr><td><code>REASONER_OUTPUT_MAX_TOKENS</code></td><td>1&nbsp;200</td><td>Longueur maximale de la réponse JSON</td></tr>
      <tr><td><code>KEYWORD_GENERATION_MAX_ATTEMPTS</code></td><td>3</td><td>Essais d'extraction des mots-clés</td></tr>
      <tr><td><code>ENABLE_DENSE_RETRIEVAL</code></td><td>oui</td><td>Recherche par le sens</td></tr>
    </tbody>
  </table></div>

  <h3>Carte du code</h3>
  <div class="ih-table-wrap"><table class="ih-table ih-table-compact">
    <tbody>
      <tr><td><code>src/pipeline.py</code></td><td>Orchestration des six étapes</td></tr>
      <tr><td><code>src/llm_ops.py</code></td><td>Prompts, schémas JSON, vérification</td></tr>
      <tr><td><code>src/llm_backend.py</code></td><td>vLLM, Gemini, OpenAI, Anthropic ; nouvelles tentatives</td></tr>
      <tr><td><code>src/retrieval.py</code>, <code>src/vector_index.py</code>, <code>src/embeddings.py</code></td><td>Recherche, index FAISS, encodage</td></tr>
      <tr><td><code>src/data_loader.py</code>, <code>src/text_utils.py</code></td><td>Lecture du corpus, normalisation de l'arabe, découpage</td></tr>
      <tr><td><code>src/reporting.py</code></td><td>Rapport HTML et résolution des références</td></tr>
      <tr><td><code>src/web_app.py</code>, <code>src/ihsan_theme.py</code>, <code>src/ui_content.py</code></td><td>Interface</td></tr>
    </tbody>
  </table></div>
  <p>Code source, installation locale et dépannage : <a href="{_e(project_url)}" target="_blank" rel="noopener">dépôt GitHub</a>.</p>
</article>
"""


# --------------------------------------------------------------------------
# Page « Le corpus »
# --------------------------------------------------------------------------

def corpus_html() -> str:
    cat = load_catalog()
    books = cat.get("books") or []
    if not books:
        return '<div class="ih-empty">Le catalogue du corpus est introuvable (src/corpus_catalog.json).</div>'

    deaths = [b.get("main_author_death_hijri") for b in books if b.get("main_author_death_hijri")]
    lo = (min(deaths) // 100) * 100
    hi = ((max(deaths) // 100) + 1) * 100

    def pos(year) -> float:
        return 100.0 * (year - lo) / max(1, hi - lo)

    ticks = "".join(
        f'<span class="tick" style="left:{pos(y):.2f}%"><span>{y}</span></span>' for y in range(lo, hi + 1, 100)
    )
    dots = "".join(
        f'<span class="ih-tl-dot" style="left:{pos(b["main_author_death_hijri"]):.2f}%" '
        f'title="{_e(b.get("title_latin"))} — {_e(b.get("author_latin"))} (m. {b["main_author_death_hijri"]} H)"></span>'
        for b in books
        if b.get("main_author_death_hijri")
    )

    cards = []
    for b in books:
        authors = " · ".join(
            f'{_e(a["name"])}' + (f' <span class="ih-muted">(m. {a["death_hijri"]} H)</span>' if a.get("death_hijri") else "")
            for a in b.get("authors") or []
        )
        facts = [f"{b.get('volumes')} vol." if b.get("volumes") else "", f"{_fmt_int(b.get('indexed_pages') or 0)} pages indexées"]
        edition = " — ".join(x for x in (b.get("publisher"), b.get("edition")) if x)
        bio = "".join(f"<li lang=\"ar\" dir=\"rtl\">{_e(line)}</li>" for line in b.get("author_bio") or [])
        cards.append(
            f"""
<article class="ih-book" id="ih-book-{_e(b['source_id'])}">
  <div class="ih-book-year">{_e(b.get('main_author_death_hijri') or '')}<span>H</span></div>
  <div class="ih-book-body">
    <h4 lang="ar" dir="rtl">{_e(b['title'])}</h4>
    <p class="ih-book-latin">{_e(b.get('title_latin'))}</p>
    <p class="ih-book-author">{_e(b.get('author_latin'))} <span class="ih-book-author-ar" lang="ar" dir="rtl">{authors}</span></p>
    <p class="ih-book-facts">{' · '.join(f for f in facts if f)} · référence <code>{_e(b['source_id'])}</code></p>
    <details><summary>Édition et auteur</summary>
      {f'<p class="ih-book-edition" lang="ar" dir="rtl">{_e(edition)}</p>' if edition else ''}
      {f'<ul class="ih-book-bio">{bio}</ul>' if bio else ''}
    </details>
  </div>
</article>"""
        )

    return f"""
<section class="ih-corpus">
  <div class="ih-stats">
    <div><strong>{cat.get('book_count')}</strong><span>ouvrages</span></div>
    <div><strong>{_fmt_int(cat.get('total_pages') or 0)}</strong><span>pages indexées</span></div>
    <div><strong>{_fmt_int(cat.get('total_passages') or 0)}</strong><span>passages consultables</span></div>
  </div>
  <p class="ih-doc-lead">Les ouvrages sont classés par date de décès de leur auteur principal, du Tabṣira
  d'al-Lakhmī (m. 478 H) au Thamar al-Dānī (m. 1335 H) : huit siècles de l'école, des grands commentaires
  anciens aux gloses tardives du Mukhtaṣar de Khalīl.</p>
  <div class="ih-timeline" aria-hidden="true"><div class="axis"></div>{ticks}{dots}</div>
  <p class="ih-timeline-caption">Siècles de l'Hégire (date de décès de l'auteur principal)</p>
  <div class="ih-books">{''.join(cards)}</div>
</section>
"""
