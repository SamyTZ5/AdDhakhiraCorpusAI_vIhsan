"""Page de connexion aux couleurs d'Ad-Dhakhira, pour la version en ligne.

Remplace la page de connexion standard de Gradio :
  - identifiant + mot de passe, un compte par personne ;
  - une session signée valable 14 jours, y compris après la mise en veille du
    serveur (la signature dérive du mot de passe de la personne : changer son
    mot de passe la déconnecte, sans toucher aux autres) ;
  - un frein aux essais répétés (10 échecs en 10 minutes par adresse).

Comptes : secret APP_USERS, une ligne « identifiant:motdepasse » par personne
(les virgules sont aussi acceptées comme séparateur).

Usage : protect(fastapi_app, parse_users(texte)) avant de monter Gradio.
"""

import hashlib
import hmac
import html
import time
import urllib.parse

COOKIE_NAME = "addhakhira_session"
SESSION_SECONDS = 14 * 24 * 3600
MAX_FAILURES = 10
FAILURE_WINDOW_SECONDS = 10 * 60
FONTS_URL = (
    "https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&"
    "family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500&"
    "family=Source+Sans+3:wght@400;600&display=swap"
)


_USERS = {}  # identifiant -> mot de passe, renseigné par protect()


def parse_users(raw: str) -> dict:
    """« alice:mdp1\nbob:mdp2 » (ou séparés par des virgules) -> {"alice": "mdp1", ...}."""
    users = {}
    for line in (raw or "").replace(",", "\n").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        name, password = line.split(":", 1)
        if name.strip() and password.strip():
            users[name.strip()] = password.strip()
    return users


def _key(username: str, password: str) -> bytes:
    return hashlib.sha256(f"addhakhira-login-v2:{username}:{password}".encode("utf-8")).digest()


def make_session(username: str, password: str, now: float = None) -> str:
    expires = int((now or time.time()) + SESSION_SECONDS)
    payload = f"v2:{username.encode('utf-8').hex()}:{expires}"
    signature = hmac.new(_key(username, password), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def session_user(value: str, users: dict = None, now: float = None) -> str:
    """Identifiant si la session est valide, sinon chaîne vide."""
    users = _USERS if users is None else users
    try:
        version, user_hex, expires, signature = (value or "").split(":", 3)
        username = bytes.fromhex(user_hex).decode("utf-8")
        password = users.get(username)
        if version != "v2" or password is None or int(expires) <= (now or time.time()):
            return ""
        payload = f"{version}:{user_hex}:{expires}"
        expected = hmac.new(_key(username, password), payload.encode(), hashlib.sha256).hexdigest()
        return username if hmac.compare_digest(signature, expected) else ""
    except (ValueError, TypeError):
        return ""


def login_page_html(error: str = "", username: str = "") -> str:
    error_html = f'<p class="error" role="alert">{html.escape(error)}</p>' if error else ""
    username_value = html.escape(username, quote=True)
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#3F0F18">
<title>Connexion · Ad-Dhakhira</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS_URL}">
<style>
  :root {{
    --bordeaux: #6B1D2A; --bordeaux-deep: #3F0F18; --gold: #B8955A; --gold-soft: #E6D5B0;
    --paper: #F8F3EA; --card: #FFFCF6; --ink: #2A1B17; --muted: #75655C; --line: #E4D7C3;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; min-height: 100%; }}
  body {{
    min-height: 100vh; display: grid; place-items: center; padding: 24px 16px;
    background: var(--paper); color: var(--ink);
    font-family: "Source Sans 3", system-ui, -apple-system, "Segoe UI", sans-serif;
  }}
  main {{ width: min(440px, 100%); }}
  .panel {{
    position: relative; background: var(--bordeaux-deep); color: var(--gold-soft);
    padding: 40px 32px 34px; text-align: center;
  }}
  .panel::before {{
    content: ""; position: absolute; inset: 9px; border: 1px solid rgba(184, 149, 90, .55);
    pointer-events: none;
  }}
  .corner {{ position: absolute; width: 20px; height: 20px; border: 0 solid var(--gold); }}
  .tl {{ top: 15px; left: 15px; border-top-width: 2px; border-left-width: 2px; }}
  .tr {{ top: 15px; right: 15px; border-top-width: 2px; border-right-width: 2px; }}
  .bl {{ bottom: 15px; left: 15px; border-bottom-width: 2px; border-left-width: 2px; }}
  .br {{ bottom: 15px; right: 15px; border-bottom-width: 2px; border-right-width: 2px; }}
  .arabic {{
    font-family: "Amiri", "Noto Naskh Arabic", serif; font-size: 3rem; line-height: 1.2;
    color: var(--gold); margin: 0 0 8px;
  }}
  h1 {{
    font-family: "Cormorant Garamond", Georgia, serif; font-weight: 500; font-size: 1.9rem;
    line-height: 1.2; margin: 0; color: #FBF4E6;
  }}
  h1 em {{ color: var(--gold-soft); }}
  form {{
    background: var(--card); border: 1px solid var(--line); border-top: 0;
    padding: 26px 28px 24px;
  }}
  label {{ display: block; font-weight: 600; margin: 0 0 8px; }}
  .field + .field {{ margin-top: 16px; }}
  input {{
    width: 100%; min-height: 48px; padding: 10px 12px; font: inherit; font-size: 1.05rem;
    color: var(--ink); background: #fff; border: 1px solid var(--line); border-radius: 2px;
  }}
  input:focus {{ outline: none; border-color: var(--gold); box-shadow: 0 0 0 3px rgba(184, 149, 90, .25); }}
  button {{
    width: 100%; min-height: 50px; margin-top: 18px; border: 0; border-radius: 2px;
    background: var(--bordeaux); color: #fff; cursor: pointer;
    font-family: "Cormorant Garamond", Georgia, serif; font-size: 1.3rem; font-weight: 600;
  }}
  button:hover {{ background: #561520; }}
  button:focus-visible {{ outline: 2px solid var(--gold); outline-offset: 3px; }}
  .help {{ margin: 14px 0 0; font-size: .9rem; color: var(--muted); line-height: 1.5; }}
  .error {{
    margin: 0 0 16px; padding: 10px 12px; border-left: 3px solid var(--bordeaux);
    background: #FBF1F2; color: var(--bordeaux); font-weight: 600;
  }}
  footer {{ margin-top: 18px; text-align: center; font-size: .85rem; color: var(--muted); }}
</style>
</head>
<body>
<main>
  <div class="panel">
    <span class="corner tl"></span><span class="corner tr"></span>
    <span class="corner bl"></span><span class="corner br"></span>
    <p class="arabic" lang="ar" dir="rtl">الذخيرة</p>
    <h1>Assistant de recherche <em>dans le fiqh mālikite.</em></h1>
  </div>
  <form method="post" action="/login">
    {error_html}
    <div class="field">
      <label for="username">Identifiant</label>
      <input id="username" name="username" autocomplete="username" autocapitalize="none" spellcheck="false"
             value="{username_value}" required {"" if username else "autofocus"}>
    </div>
    <div class="field">
      <label for="password">Mot de passe</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required
             {"autofocus" if username else ""}>
    </div>
    <button type="submit">Se connecter</button>
    <p class="help">Accès réservé : votre identifiant et votre mot de passe vous ont été communiqués avec le
    lien de l'outil. Vous resterez connecté 14 jours sur cet appareil.</p>
  </form>
  <footer>Outil de recherche bibliographique : il ne délivre pas de fatwa.</footer>
</main>
</body>
</html>"""


def protect(app, users: dict) -> None:
    """Ajoute la page de connexion et exige une session valide pour tout le reste."""
    _USERS.clear()
    _USERS.update(users)
    from fastapi import Request
    from fastapi.responses import HTMLResponse, RedirectResponse

    failures = {}  # adresse -> liste des horodatages d'échec

    def _recent_failures(address: str) -> list:
        now = time.time()
        recent = [t for t in failures.get(address, []) if now - t < FAILURE_WINDOW_SECONDS]
        failures[address] = recent
        return recent

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        if request.url.path in ("/login", "/logout"):
            return await call_next(request)
        if session_user(request.cookies.get(COOKIE_NAME, "")):
            return await call_next(request)
        if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/login", status_code=303)
        return HTMLResponse("Connexion requise.", status_code=401)

    @app.get("/login", response_class=HTMLResponse)
    async def login_form(request: Request):
        if session_user(request.cookies.get(COOKIE_NAME, "")):
            return RedirectResponse("/", status_code=303)
        return HTMLResponse(login_page_html())

    @app.post("/login", response_class=HTMLResponse)
    async def login_submit(request: Request):
        address = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
            request.client.host if request.client else "inconnue"
        )
        if len(_recent_failures(address)) >= MAX_FAILURES:
            return HTMLResponse(
                login_page_html("Trop d'essais. Patientez une dizaine de minutes avant de réessayer."),
                status_code=429,
            )
        body = (await request.body()).decode("utf-8", errors="replace")
        form = urllib.parse.parse_qs(body, keep_blank_values=True)
        username = form.get("username", [""])[0].strip()
        given = form.get("password", [""])[0]
        expected = _USERS.get(username)
        # Comparaison à temps constant, même pour un identifiant inconnu.
        valid = hmac.compare_digest(given.encode("utf-8"), (expected or "\0" * 32).encode("utf-8"))
        if expected is None or not valid:
            failures.setdefault(address, []).append(time.time())
            return HTMLResponse(
                login_page_html("Identifiant ou mot de passe incorrect.", username), status_code=401
            )
        failures.pop(address, None)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            make_session(username, expected),
            max_age=SESSION_SECONDS,
            httponly=True,
            secure=True,
            samesite="lax",
        )
        return response

    @app.get("/logout")
    async def logout():
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(COOKIE_NAME)
        return response
