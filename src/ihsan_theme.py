"""Identité visuelle de l'interface Gradio (DA inspirée d'institut-ihsan.org).

Tout ce qui touche à l'apparence est centralisé ici : couleurs, polices,
en-tête, pied de page et affichage de la synthèse. Le notebook Colab et
src/web_app.py importent ce module, il suffit donc de modifier ce fichier
pour faire évoluer la DA partout.

Pour ajuster une couleur, modifie seulement le dictionnaire PALETTE.
"""

import html as _html

import gradio as gr


# --------------------------------------------------------------------------
# 1. Palette et polices
# --------------------------------------------------------------------------

PALETTE = {
    "bordeaux": "#6B1D2A",       # couleur principale (titres, bouton)
    "bordeaux_deep": "#3F0F18",  # fond de l'en-tête
    "bordeaux_hover": "#561520",
    "gold": "#B8955A",           # filets, ornements, numéros de section
    "gold_soft": "#E6D5B0",      # texte doré sur fond bordeaux
    "paper": "#F8F3EA",          # fond de page
    "card": "#FFFCF6",           # fond des blocs
    "ink": "#2A1B17",            # texte principal
    "muted": "#75655C",          # texte secondaire
    "line": "#E4D7C3",           # bordures
}

FONT_DISPLAY = "Cormorant Garamond"  # titres
FONT_BODY = "Source Sans 3"          # texte courant et formulaires
FONT_ARABIC = "Amiri"                # texte arabe

GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Amiri:wght@400;700&"
    "family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500;1,600&"
    "family=Source+Sans+3:wght@400;600&display=swap"
)

PROJECT_URL = "https://github.com/SamyTZ5/AdDhakhiraCorpusAI_vIhsan"
UPSTREAM_URL = "https://github.com/git-haddadz/AdDhakhiraCorpusAI"


# --------------------------------------------------------------------------
# 2. Thème Gradio
# --------------------------------------------------------------------------

def _bordeaux_scale() -> gr.themes.Color:
    return gr.themes.Color(
        name="ihsan_bordeaux",
        c50="#FBF2F3", c100="#F4DFE2", c200="#E8BFC5", c300="#D495A0",
        c400="#B8606F", c500="#8F3342", c600="#6B1D2A", c700="#561520",
        c800="#3F0F18", c900="#2C0A10", c950="#1C060A",
    )


def build_theme() -> gr.themes.Base:
    p = PALETTE
    theme = gr.themes.Base(
        primary_hue=_bordeaux_scale(),
        neutral_hue=gr.themes.colors.stone,
        font=[gr.themes.GoogleFont(FONT_BODY), "system-ui", "sans-serif"],
        font_mono=["ui-monospace", "monospace"],
        radius_size=gr.themes.sizes.radius_sm,
    )
    values = {
        "body_background_fill": p["paper"],
        "body_text_color": p["ink"],
        "body_text_color_subdued": p["muted"],
        "background_fill_primary": p["card"],
        "background_fill_secondary": p["paper"],
        "border_color_primary": p["line"],
        "color_accent": p["bordeaux"],
        "color_accent_soft": "#F4DFE2",
        "link_text_color": p["bordeaux"],
        "link_text_color_hover": p["bordeaux_hover"],
        "link_text_color_visited": p["bordeaux"],
        "block_background_fill": p["card"],
        "block_border_color": p["line"],
        "block_border_width": "1px",
        "block_label_background_fill": "transparent",
        "block_label_text_color": p["ink"],
        "block_label_text_weight": "600",
        "block_title_text_color": p["ink"],
        "block_info_text_color": p["muted"],
        "block_shadow": "none",
        "input_background_fill": "#FFFFFF",
        "input_border_color": p["line"],
        "input_border_color_focus": p["gold"],
        "input_shadow_focus": f"0 0 0 3px {p['gold']}33",
        "input_placeholder_color": "#A89A90",
        "checkbox_background_color_selected": p["bordeaux"],
        "checkbox_border_color_selected": p["bordeaux"],
        "checkbox_label_background_fill": p["card"],
        "checkbox_label_background_fill_selected": p["card"],
        "checkbox_label_text_color": p["ink"],
        "checkbox_label_text_color_selected": p["ink"],
        "button_primary_background_fill": p["bordeaux"],
        "button_primary_background_fill_hover": p["bordeaux_hover"],
        "button_primary_text_color": "#FFFFFF",
        "button_primary_border_color": p["bordeaux"],
        "button_secondary_background_fill": p["card"],
        "button_secondary_background_fill_hover": "#F3EBDD",
        "button_secondary_text_color": p["bordeaux"],
        "button_secondary_border_color": p["gold"],
        "panel_background_fill": p["card"],
        "panel_border_color": p["line"],
        "accordion_text_color": p["ink"],
        "table_border_color": p["line"],
        "loader_color": p["gold"],
        "shadow_drop": "none",
        "shadow_drop_lg": "none",
    }
    # L'identité Ihsan reste claire, même si l'appareil est en mode sombre.
    values.update({
        f"{key}_dark": value
        for key, value in list(values.items())
        if hasattr(theme, f"{key}_dark")
    })
    return theme.set(**values)


# --------------------------------------------------------------------------
# 3. Feuille de style
# --------------------------------------------------------------------------

def build_css() -> str:
    p = PALETTE
    return f"""
:root {{
  --ih-bordeaux: {p['bordeaux']};
  --ih-bordeaux-deep: {p['bordeaux_deep']};
  --ih-gold: {p['gold']};
  --ih-gold-soft: {p['gold_soft']};
  --ih-paper: {p['paper']};
  --ih-card: {p['card']};
  --ih-ink: {p['ink']};
  --ih-muted: {p['muted']};
  --ih-line: {p['line']};
  --ih-display: "{FONT_DISPLAY}", "Cormorant", Georgia, serif;
  --ih-arabic: "{FONT_ARABIC}", "Noto Naskh Arabic", "Times New Roman", serif;
}}

.gradio-container {{
  max-width: 880px !important;
  margin: 0 auto !important;
  padding: 24px 20px 40px !important;
}}

/* Les blocs HTML personnalisés s'alignent sur les champs du formulaire. */
.html-container {{
  padding: 0 !important;
}}

/* ---------- En-tête ---------- */
#ih-header {{
  position: relative;
  background: var(--ih-bordeaux-deep);
  color: var(--ih-gold-soft);
  padding: 44px 40px 40px;
  text-align: center;
  margin-bottom: 12px;
}}
#ih-header::before {{
  content: "";
  position: absolute;
  inset: 10px;
  border: 1px solid rgba(184, 149, 90, .55);
  pointer-events: none;
}}
.ih-corner {{
  position: absolute;
  width: 22px;
  height: 22px;
  border-color: var(--ih-gold);
  border-style: solid;
  border-width: 0;
}}
.ih-corner.tl {{ top: 16px; left: 16px; border-top-width: 2px; border-left-width: 2px; }}
.ih-corner.tr {{ top: 16px; right: 16px; border-top-width: 2px; border-right-width: 2px; }}
.ih-corner.bl {{ bottom: 16px; left: 16px; border-bottom-width: 2px; border-left-width: 2px; }}
.ih-corner.br {{ bottom: 16px; right: 16px; border-bottom-width: 2px; border-right-width: 2px; }}
.ih-arabic-title {{
  font-family: var(--ih-arabic);
  font-size: clamp(2.6rem, 7vw, 3.6rem);
  line-height: 1.2;
  color: var(--ih-gold);
  margin: 0 0 12px;
}}
.ih-kicker {{
  font-size: .95rem;
  letter-spacing: .04em;
  color: var(--ih-gold-soft);
  margin: 6px 0 18px;
}}
#ih-header h1 {{
  font-family: var(--ih-display);
  font-weight: 500;
  font-size: clamp(1.9rem, 4.6vw, 2.6rem);
  line-height: 1.15;
  color: #FBF4E6;
  margin: 0 0 14px;
}}
#ih-header h1 em {{
  font-style: italic;
  color: var(--ih-gold-soft);
}}
.ih-lead {{
  max-width: 34em;
  margin: 0 auto;
  font-size: 1.02rem;
  line-height: 1.6;
  color: rgba(251, 244, 230, .82);
}}

/* ---------- Titres de section ---------- */
.ih-section {{
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin: 0 0 4px;
  padding: 30px 0 8px;
  border-bottom: 1px solid var(--ih-line);
}}
.ih-section .ih-num {{
  font-family: var(--ih-display);
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--ih-gold);
  min-width: 1.6em;
}}
.ih-section h2 {{
  font-family: var(--ih-display);
  font-size: 1.65rem;
  font-weight: 600;
  color: var(--ih-bordeaux);
  margin: 0;
}}
.ih-section p {{
  margin: 0 0 0 auto;
  font-size: .9rem;
  color: var(--ih-muted);
  text-align: right;
}}

/* ---------- Formulaire ---------- */
#ih-question textarea {{
  font-size: 1.08rem !important;
  line-height: 1.6 !important;
  unicode-bidi: plaintext;
}}
#ih-question textarea:lang(ar), #ih-question textarea[dir="rtl"] {{
  font-family: var(--ih-arabic) !important;
}}
#ih-submit {{
  font-family: var(--ih-display) !important;
  font-size: 1.25rem !important;
  font-weight: 600 !important;
  letter-spacing: .01em;
  padding: 12px 20px !important;
  min-height: 52px;
}}
#ih-submit:focus-visible, #ih-download:focus-visible {{
  outline: 2px solid var(--ih-gold) !important;
  outline-offset: 3px;
}}
#ih-advanced .label-wrap span {{
  color: var(--ih-muted);
}}

/* ---------- Statut et réponse ---------- */
#run-status {{
  min-height: 1.5em;
}}
#ih-download {{
  border: 1px solid var(--ih-gold) !important;
  font-weight: 600 !important;
}}
#run-status .ih-progress-idle p {{
  margin: 14px 0 0;
  padding-left: 14px;
  border-left: 2px solid var(--ih-gold);
  color: var(--ih-muted);
  font-style: italic;
}}
#ih-answer iframe.ih-report {{
  display: block;
  width: 100%;
  min-height: 480px;
  border: 1px solid var(--ih-line);
  background: var(--ih-paper);
}}
.ih-empty {{
  padding: 34px 24px;
  text-align: center;
  color: var(--ih-muted);
  border: 1px dashed var(--ih-line);
  background: var(--ih-card);
}}
.ih-empty .ih-arabic-mark {{
  display: block;
  font-family: var(--ih-arabic);
  font-size: 1.8rem;
  color: var(--ih-gold);
  margin-bottom: 6px;
}}

/* ---------- Pied de page ---------- */
#ih-footer {{
  margin-top: 40px;
  text-align: center;
  font-size: .9rem;
  color: var(--ih-muted);
  line-height: 1.6;
}}
.ih-rule {{
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 auto 16px;
  max-width: 260px;
}}
.ih-rule::before, .ih-rule::after {{
  content: "";
  flex: 1;
  height: 1px;
  background: var(--ih-gold);
}}
.ih-rule span {{
  width: 8px;
  height: 8px;
  background: var(--ih-gold);
  transform: rotate(45deg);
}}
#ih-footer a {{
  color: var(--ih-bordeaux);
}}

/* ---------- Onglets ---------- */
#ih-tabs {{
  margin-top: 6px;
}}
#ih-tabs button[role="tab"] {{
  font-family: var(--ih-display) !important;
  font-size: 1.15rem !important;
  font-weight: 600 !important;
  color: var(--ih-muted) !important;
  border: 0 !important;
  border-bottom: 2px solid transparent !important;
  background: transparent !important;
  padding: 10px 16px !important;
}}
#ih-tabs .tab-container {{
  flex-wrap: wrap;
  min-width: 0;
  max-width: 100%;
}}
#ih-tabs button[role="tab"]:hover {{
  color: var(--ih-bordeaux) !important;
}}
#ih-tabs button[role="tab"][aria-selected="true"] {{
  color: var(--ih-bordeaux) !important;
  border-bottom-color: var(--ih-gold) !important;
}}
#ih-tabs button[role="tab"]:focus-visible {{
  outline: 2px solid var(--ih-gold) !important;
  outline-offset: 2px;
}}

/* ---------- Pages de documentation ---------- */
.ih-doc {{
  max-width: 44em;
  line-height: 1.7;
  font-size: 1.02rem;
  color: var(--ih-ink);
  padding: 8px 0 12px;
}}
.ih-doc-lead {{
  font-family: var(--ih-display);
  font-size: 1.35rem;
  line-height: 1.5;
  color: var(--ih-ink);
  margin: 14px 0 18px;
}}
.ih-doc h3 {{
  font-family: var(--ih-display);
  font-size: 1.45rem;
  font-weight: 600;
  color: var(--ih-bordeaux);
  margin: 28px 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--ih-line);
}}
.ih-doc p, .ih-doc li, .ih-doc dd {{
  color: var(--ih-ink);
}}
.ih-doc ul {{
  padding-left: 1.2em;
}}
.ih-doc li {{
  margin: 6px 0;
}}
.ih-doc [lang="ar"] {{
  font-family: var(--ih-arabic);
  font-size: 1.1em;
}}
.ih-doc code {{
  font-size: .85em;
  background: #F3EBDD;
  padding: 1px 5px;
  color: var(--ih-bordeaux);
}}
.ih-doc a {{
  color: var(--ih-bordeaux);
}}
.ih-dl {{
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 8px 20px;
  margin: 8px 0;
}}
.ih-dl dt {{
  font-weight: 600;
  color: var(--ih-bordeaux);
}}
.ih-dl dd {{
  margin: 0;
}}
.ih-pipeline {{
  list-style: none;
  counter-reset: step;
  padding: 0;
  margin: 12px 0;
}}
.ih-pipeline li {{
  list-style: none !important;
  counter-increment: step;
  position: relative;
  padding: 0 0 18px 52px;
  margin: 0;
}}
.ih-pipeline li::before {{
  content: counter(step);
  position: absolute;
  left: 0;
  top: 0;
  width: 34px;
  height: 34px;
  border: 1px solid var(--ih-gold);
  color: var(--ih-bordeaux);
  font-family: var(--ih-display);
  font-weight: 600;
  font-size: 1.1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ih-card);
}}
.ih-pipeline li::marker {{
  content: "";
}}
.ih-pipeline li:not(:last-child)::after {{
  content: "";
  position: absolute;
  left: 17px;
  top: 36px;
  bottom: 2px;
  width: 1px;
  background: var(--ih-line);
}}
.ih-table-wrap {{
  overflow-x: auto;
  margin: 10px 0;
}}
.ih-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: .93rem;
}}
.ih-table th, .ih-table td {{
  border: 1px solid var(--ih-line);
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
  color: var(--ih-ink);
}}
.ih-table th {{
  background: #F3EBDD;
  color: var(--ih-bordeaux);
  font-weight: 600;
}}
.ih-table-compact td:first-child {{
  white-space: nowrap;
}}

/* ---------- Corpus ---------- */
.ih-stats {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border: 1px solid var(--ih-line);
  background: var(--ih-card);
  margin: 16px 0 6px;
}}
.ih-stats div {{
  padding: 16px 12px;
  text-align: center;
}}
.ih-stats div + div {{
  border-left: 1px solid var(--ih-line);
}}
.ih-stats strong {{
  display: block;
  font-family: var(--ih-display);
  font-size: 2rem;
  font-weight: 600;
  color: var(--ih-bordeaux);
  line-height: 1.1;
}}
.ih-stats span {{
  font-size: .88rem;
  color: var(--ih-muted);
}}
.ih-timeline {{
  position: relative;
  height: 52px;
  margin: 18px 12px 0;
}}
.ih-timeline .axis {{
  position: absolute;
  left: 0;
  right: 0;
  top: 16px;
  height: 1px;
  background: var(--ih-gold);
}}
.ih-timeline .tick {{
  position: absolute;
  top: 10px;
  width: 1px;
  height: 13px;
  background: var(--ih-gold);
}}
.ih-timeline .tick span {{
  position: absolute;
  top: 18px;
  left: 50%;
  transform: translateX(-50%);
  font-size: .78rem;
  color: var(--ih-muted);
}}
.ih-timeline .ih-tl-dot {{
  display: block;
  box-sizing: border-box;
  padding: 0 !important;
  text-decoration: none;
  position: absolute;
  top: 11px;
  width: 11px;
  height: 11px;
  margin-left: -5.5px;
  background: var(--ih-bordeaux);
  border: 2px solid var(--ih-paper);
  transform: rotate(45deg);
}}
.ih-timeline .ih-tl-dot:hover, .ih-timeline .ih-tl-dot:focus-visible {{
  background: var(--ih-gold);
  outline: none;
}}
.ih-timeline-caption {{
  text-align: center;
  font-size: .82rem;
  color: var(--ih-muted);
  margin: 0 0 18px;
}}
.ih-books {{
  border-top: 1px solid var(--ih-line);
}}
.ih-book {{
  display: grid;
  grid-template-columns: 76px 1fr;
  gap: 16px;
  padding: 16px 0;
  border-bottom: 1px solid var(--ih-line);
  scroll-margin-top: 20px;
}}
.ih-book:target {{
  background: #FBF3E4;
}}
.ih-book-year {{
  font-family: var(--ih-display);
  font-size: 1.6rem;
  font-weight: 600;
  color: var(--ih-gold);
  text-align: right;
  line-height: 1.1;
}}
.ih-book-year span {{
  display: block;
  font-size: .8rem;
  color: var(--ih-muted);
}}
.ih-book h4 {{
  font-family: var(--ih-arabic);
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--ih-bordeaux);
  margin: 0;
  text-align: left;
}}
.ih-book p {{
  margin: 3px 0;
  color: var(--ih-ink);
}}
.ih-book-latin {{
  font-family: var(--ih-display);
  font-style: italic;
  font-size: 1.12rem;
}}
.ih-book-author {{
  font-size: .95rem;
}}
.ih-book-author-ar {{
  font-family: var(--ih-arabic);
  color: var(--ih-muted);
  margin-left: 6px;
}}
.ih-muted {{
  color: var(--ih-muted);
}}
.ih-book-facts {{
  font-size: .85rem;
  color: var(--ih-muted) !important;
}}
.ih-book details {{
  margin-top: 6px;
}}
.ih-book summary {{
  cursor: pointer;
  font-size: .88rem;
  color: var(--ih-bordeaux);
}}
.ih-book-edition, .ih-book-bio li {{
  font-family: var(--ih-arabic);
  font-size: 1rem;
  line-height: 1.8;
}}
.ih-book-bio {{
  margin: 6px 0 0;
  padding-right: 1.2em;
}}

/* ---------- Exemples de questions ---------- */
#ih-examples {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 2px 0 6px;
}}
#ih-examples button {{
  font-size: .9rem !important;
  font-weight: 400 !important;
  padding: 6px 12px !important;
  border: 1px solid var(--ih-line) !important;
  background: var(--ih-card) !important;
  color: var(--ih-ink) !important;
  min-width: 0 !important;
  flex: 0 1 auto !important;
  width: auto !important;
  max-width: 100% !important;
  white-space: normal !important;
  text-align: start !important;
  unicode-bidi: plaintext;
}}
#ih-examples button:hover {{
  border-color: var(--ih-gold) !important;
  color: var(--ih-bordeaux) !important;
}}
.ih-examples-label {{
  font-size: .88rem;
  color: var(--ih-muted);
  margin: 6px 0 4px;
}}

/* ---------- Jauge d'avancement ---------- */
.ih-progress {{
  margin: 14px 0 0;
  padding: 16px 18px 14px;
  background: var(--ih-card);
  border: 1px solid var(--ih-line);
}}
.ih-progress-idle {{
  background: transparent;
  border: 0;
  padding: 6px 0 0;
}}
.ih-progress-idle .ih-progress-msg {{
  font-style: italic;
}}
.ih-progress-error {{
  border-color: var(--ih-bordeaux);
  border-left-width: 3px;
}}
.ih-steps {{
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  list-style: none;
  padding: 0;
  margin: 0 0 12px;
}}
.ih-steps li {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  font-size: .8rem;
  color: var(--ih-muted);
  position: relative;
  margin: 0;
  text-align: center;
}}
.ih-steps li:not(:first-child)::before {{
  content: "";
  position: absolute;
  top: 6px;
  right: 50%;
  width: 100%;
  height: 1px;
  background: var(--ih-line);
  z-index: 0;
}}
.ih-steps li.done:not(:first-child)::before, .ih-steps li.current:not(:first-child)::before, .ih-steps li.error:not(:first-child)::before {{
  background: var(--ih-gold);
}}
.ih-steps .ih-step-mark {{
  width: 13px;
  height: 13px;
  transform: rotate(45deg);
  border: 1px solid var(--ih-line);
  background: var(--ih-card);
  position: relative;
  z-index: 1;
}}
.ih-steps li.done .ih-step-mark {{
  background: var(--ih-gold);
  border-color: var(--ih-gold);
}}
.ih-steps li.current .ih-step-mark {{
  background: var(--ih-bordeaux);
  border-color: var(--ih-bordeaux);
}}
.ih-steps li.error .ih-step-mark {{
  background: var(--ih-card);
  border: 2px solid var(--ih-bordeaux);
}}
.ih-steps li.current, .ih-steps li.error {{
  color: var(--ih-bordeaux);
  font-weight: 600;
}}
.ih-bar {{
  height: 6px;
  background: #EFE5D4;
  overflow: hidden;
}}
.ih-bar-fill {{
  height: 100%;
  width: var(--to);
  background: var(--ih-bordeaux);
  animation: ih-grow 8s ease-out;
}}
.ih-progress-done .ih-bar-fill {{
  background: var(--ih-gold);
  animation: none;
}}
.ih-progress-error .ih-bar-fill {{
  animation: none;
  opacity: .45;
}}
@keyframes ih-grow {{
  from {{ width: var(--from); }}
  to {{ width: var(--to); }}
}}
.ih-progress-meta {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 16px;
  margin-top: 10px;
}}
.ih-progress-msg {{
  margin: 0;
  color: var(--ih-ink);
  font-size: .95rem;
}}
.ih-progress-time {{
  flex: none;
  font-size: .85rem;
  color: var(--ih-muted);
  font-variant-numeric: tabular-nums;
}}
.ih-progress-done .ih-progress-time, .ih-progress-error .ih-progress-time {{
  color: var(--ih-bordeaux);
  font-weight: 600;
}}
.ih-progress-sources {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  font-size: .85rem;
  color: var(--ih-muted);
}}
.ih-progress-sources > span:first-child {{
  margin-right: 4px;
}}
.ih-chip {{
  font-family: var(--ih-arabic);
  font-size: .98rem;
  color: var(--ih-bordeaux);
  border: 1px solid var(--ih-gold);
  padding: 0 8px;
  background: #FFFDF7;
}}
.ih-progress-hint {{
  margin: 8px 0 0;
  font-size: .85rem;
  color: var(--ih-muted);
  font-style: italic;
}}

@media (max-width: 640px) {{
  body .gradio-container {{ padding: 12px 12px 28px !important; }}
  body .gradio-container .main {{ padding: 8px 0 !important; }}
  #ih-header {{ padding: 36px 22px 32px; }}
  .ih-section {{ flex-wrap: wrap; }}
  .ih-section p {{ margin-left: 0; text-align: left; width: 100%; }}
  .ih-steps .lbl {{ font-size: .75rem; white-space: nowrap; }}
  .ih-steps li:not(.current):not(.error) .lbl {{ visibility: hidden; }}
  #ih-tabs button[role="tab"] {{ padding: 8px 10px !important; font-size: 1.02rem !important; }}
  .ih-progress-meta {{ flex-direction: column; gap: 4px; }}
  .ih-stats strong {{ font-size: 1.5rem; }}
  .ih-book {{ grid-template-columns: 1fr; gap: 4px; }}
  .ih-book-year {{ text-align: left; }}
  .ih-dl {{ grid-template-columns: 1fr; gap: 2px; }}
  .ih-dl dd {{ margin-bottom: 8px; }}
}}

@media (prefers-reduced-motion: reduce) {{
  * {{ transition: none !important; animation: none !important; }}
}}
"""


# --------------------------------------------------------------------------
# 4. Blocs HTML
# --------------------------------------------------------------------------

HEAD = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    f'<link rel="stylesheet" href="{GOOGLE_FONTS_URL}">'
    '<meta name="theme-color" content="#3F0F18">'
)

# Force l'affichage clair : la DA Ihsan est pensée sur fond clair.
FORCE_LIGHT_JS = """
() => {
  document.body.classList.remove('dark');
  document.documentElement.style.colorScheme = 'light';
}
"""


def header_html() -> str:
    return """
<header id="ih-header">
  <span class="ih-corner tl"></span><span class="ih-corner tr"></span>
  <span class="ih-corner bl"></span><span class="ih-corner br"></span>
  <p class="ih-arabic-title" lang="ar" dir="rtl">الذخيرة</p>
  <h1>Assistant de recherche <em>dans le fiqh mālikite.</em></h1>
  <p class="ih-lead">Posez une question en arabe ou en français&nbsp;: l'assistant
  retrouve les passages pertinents dans les ouvrages de référence de l'école
  et en propose une synthèse sourcée.</p>
</header>
"""


def section_html(number: str, title: str, note: str = "") -> str:
    note_html = f"<p>{_html.escape(note)}</p>" if note else ""
    return (
        f'<div class="ih-section"><span class="ih-num">{_html.escape(number)}</span>'
        f"<h2>{_html.escape(title)}</h2>{note_html}</div>"
    )


def footer_html(project_url: str = PROJECT_URL) -> str:
    return f"""
<footer id="ih-footer">
  <div class="ih-rule" aria-hidden="true"><span></span></div>
  <p>Outil de recherche bibliographique&nbsp;: il aide à retrouver et lire les sources,
  il ne délivre pas de fatwa.</p>
  <p>Projet open source&nbsp;: <a href="{_html.escape(project_url)}" target="_blank" rel="noopener">code de cette version</a>,
  d'après <a href="{_html.escape(UPSTREAM_URL)}" target="_blank" rel="noopener">AdDhakhiraCorpusAI</a></p>
</footer>
"""


def empty_answer_html() -> str:
    return (
        '<div class="ih-empty"><span class="ih-arabic-mark" lang="ar" dir="rtl">إحسان</span>'
        "La synthèse s'affichera ici, avec les citations arabes et les pages consultées.</div>"
    )


def report_iframe(report_html: str) -> str:
    """Affiche la synthèse dans un cadre isolé.

    Le rapport est une page HTML complète, avec ses propres styles et ses
    onglets en JavaScript. Dans un cadre, ses styles ne débordent pas sur
    l'interface et ses onglets fonctionnent.
    """
    if not report_html:
        return empty_answer_html()
    if "<html" not in report_html.lower():
        return f'<div class="ih-empty">{_html.escape(report_html)}</div>'
    srcdoc = _html.escape(report_html, quote=True)
    resize = (
        "const f=this;const d=f.contentDocument;if(!d)return;"
        "const r=()=>{f.style.height=(d.body.offsetHeight+4)+'px'};"
        "r();if(window.ResizeObserver){new ResizeObserver(r).observe(d.body)}"
        "d.addEventListener('click',()=>setTimeout(r,60));"
    )
    return (
        f'<iframe class="ih-report" title="Synthèse bibliographique" '
        f'srcdoc="{srcdoc}" onload="{_html.escape(resize, quote=True)}"></iframe>'
    )


def _scoped(css: str) -> str:
    """Préfixe les règles de l'interface par .gradio-container.

    Cela leur donne la priorité sur les styles typographiques par défaut
    de Gradio (couleurs des paragraphes et titres), sans multiplier les !important.
    """
    lines = []
    for line in css.splitlines():
        stripped = line.strip()
        if "{" in stripped and stripped.startswith(("#ih-", ".ih-", "#run-status")):
            indent = line[: len(line) - len(line.lstrip())]
            selector_text, rest = stripped.split("{", 1)
            selectors = [sel.strip() for sel in selector_text.split(",")]
            line = indent + ", ".join(f".gradio-container {sel}" for sel in selectors) + " {" + rest
        lines.append(line)
    return "\n".join(lines)


def launch_kwargs() -> dict:
    """Arguments de style à passer à demo.launch() (Gradio 6).

    La feuille de style passe par `head` plutôt que par `css` : Gradio préfixe
    le paramètre `css`, ce qui empêche d'ajuster le conteneur principal sur mobile.
    """
    return {
        "theme": build_theme(),
        "head": HEAD + f"<style>{_scoped(build_css())}</style>",
        "js": FORCE_LIGHT_JS,
        "footer_links": [],
    }
