---
title: Ad-Dhakhira
emoji: 📚
colorFrom: red
colorTo: yellow
sdk: gradio
sdk_version: 6.15.1
python_version: "3.12"
app_file: app.py
pinned: false
short_description: Recherche bibliographique dans le fiqh mālikite
---

# Ad-Dhakhira

Assistant de recherche bibliographique dans le fiqh mālikite : il retrouve les
passages pertinents dans 18 ouvrages de référence et en propose une synthèse
sourcée. Il ne délivre pas de fatwa.

Le code complet se trouve sur GitHub :
https://github.com/SamyTZ5/AdDhakhiraCorpusAI_vIhsan

## Réglages du Space (Settings → Variables and secrets)

| Nom | Type | Rôle |
|---|---|---|
| `GEMINI_API_KEY` | Secret | Clé Google AI Studio utilisée pour tous les visiteurs |
| `APP_PASSWORD` | Secret | Mot de passe demandé à l'entrée (recommandé) |
| `ADDHAKHIRA_INDEX_REPO` | Variable | Dépôt de données contenant l'index, ex. `pseudo/ad-dhakhira-index` |
| `GEMINI_MODEL` | Variable | Facultatif, `gemini-3.5-flash-lite` par défaut |
