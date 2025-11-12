# app.py
from __future__ import annotations
import os, json
from pathlib import Path
from io import BytesIO
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_file, abort
)

import qrcode


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
app = Flask(__name__)

# secret key: preferisci SECRET FILE (/etc/secrets/SECRET_KEY) -> APP_SECRET -> fallback
secret_path = Path("/etc/secrets/SECRET_KEY")
if secret_path.exists():
    app.secret_key = secret_path.read_text().strip()
else:
    app.secret_key = os.getenv("APP_SECRET", "dev-secret-change-me")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
if not ADMIN_PASSWORD:
    # Senza password non vogliamo far bootare per sicurezza
    raise RuntimeError("Missing ENV ADMIN_PASSWORD")

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")


# -----------------------------------------------------------------------------
# Storage: JSON file (no DB). Ogni agente è un dict, indicizzato per slug.
# -----------------------------------------------------------------------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = DATA_DIR / "db.json"

def _load_db() -> dict:
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}  # vuoto

def _save_db(db: dict) -> None:
    tmp = DB_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DB_FILE)

DB: dict[str, dict] = _load_db()


# -----------------------------------------------------------------------------
# Utility / Template filters
# -----------------------------------------------------------------------------
@app.template_filter("ensure_http")
def ensure_http(u: str | None):
    if not u:
        return ""
    u = u.strip()
    if u.startswith(("http://", "https://")):
        return u
    return "https://" + u

def is_admin() -> bool:
    return bool(session.get("admin"))

def normalize_slug(s: str) -> str:
    return (s or "").strip().lower()


# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat()}


# -----------------------------------------------------------------------------
# Auth semplice: solo password
# -----------------------------------------------------------------------------
@app.get("/login")
def login():
    if is_admin():
        return redirect(url_for("admin_home"))
    return render_template("login.html")

@app.post("/login")
def do_login():
    pw = request.form.get("password", "")
    if pw == ADMIN_PASSWORD:
        session["admin"] = True
        return redirect(url_for("admin_home"))
    return render_template("login.html", error="Password non corretta"), 401

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -----------------------------------------------------------------------------
# Admin
# -----------------------------------------------------------------------------
@app.get("/")
def root_redirect():
    return redirect(url_for("admin_home"))

@app.get("/admin")
def admin_home():
    if not is_admin():
        return redirect(url_for("login"))
    # ordina per nome
    agents = sorted(DB.values(), key=lambda a: (a.get("name") or "").lower())
    return render_template("admin_list.html", agents=agents)

@app.get("/admin/new")
def admin_new():
    if not is_admin():
        return redirect(url_for("login"))
    return render_template("agent_form.html", agent=None, error=None)

@app.post("/admin/new")
def admin_new_post():
    if not is_admin():
        return redirect(url_for("login"))

    # campi gestiti
    fields = [
        "slug","name","company","role","bio",
        "phone_mobile","phone_office","emails","websites",
        "facebook","instagram","linkedin","tiktok",
        "telegram","whatsapp","pec","piva","sdi","addresses",
        "photo_url","gallery_urls","pdf1_url","pdf2_url","pdf3_url","pdf4_url",
    ]
    agent = {f: request.form.get(f, "").strip() for f in fields}
    agent["slug"] = normalize_slug(agent["slug"])

    if not agent["slug"]:
        return render_template("agent_form.html", agent=agent, error="Slug obbligatorio"), 400
    if agent["slug"] in DB:
        return render_template("agent_form.html", agent=agent, error="Slug già esistente"), 400

    DB[agent["slug"]] = agent
    _save_db(DB)
    return redirect(url_for("admin_home"))

@app.get("/admin/<slug>/edit")
def admin_edit(slug):
    if not is_admin():
        return redirect(url_for("login"))
    slug = normalize_slug(slug)
    agent = DB.get(slug)
    if not agent:
        return render_template("404.html"), 404
    return render_template("agent_form.html", agent=agent, error=None)

@app.post("/admin/<slug>/edit")
def admin_edit_post(slug):
    if not is_admin():
        return redirect(url_for("login"))
    old_slug = normalize_slug(slug)
    agent = DB.get(old_slug)
    if not agent:
        return render_template("404.html"), 404

    fields = [
        "slug","name","company","role","bio",
        "phone_mobile","phone_office","emails","websites",
        "facebook","instagram","linkedin","tiktok",
        "telegram","whatsapp","pec","piva","sdi","addresses",
        "photo_url","gallery_urls","pdf1_url","pdf2_url","pdf3_url","pdf4_url",
    ]
    new_data = {f: request.form.get(f, "").strip() for f in fields}
    new_slug = normalize_slug(new_data.get("slug"))

    if not new_slug:
        return render_template("agent_form.html", agent=new_data, error="Slug obbligatorio"), 400
    if new_slug != old_slug and new_slug in DB:
        return render_template("agent_form.html", agent=new_data, error="Slug già esistente"), 400

    # aggiorna/rename
    if new_slug != old_slug:
        DB.pop(old_slug, None)
    DB[new_slug] = new_data
    _save_db(DB)
    return redirect(url_for("admin_home"))

@app.post("/admin/<slug>/delete")
def admin_delete(slug):
    if not is_admin():
        return redirect(url_for("login"))
    slug = normalize_slug(slug)
    DB.pop(slug, None)
    _save_db(DB)
    return redirect(url_for("admin_home"))


# -----------------------------------------------------------------------------
# Pubblico: Card, vCard, QR
# -----------------------------------------------------------------------------
@app.get("/<slug>")
def public_card(slug):
    slug = normalize_slug(slug)
    agent = DB.get(slug)
    if not agent:
        return render_template("404.html"), 404
    return render_template("card.html", agent=agent)

@app.get("/vcard/<slug>.vcf")
def vcard(slug):
    slug = normalize_slug(slug)
    agent = DB.get(slug)
    if not agent:
        return render_template("404.html"), 404

    # vCard semplice
    name = agent.get("name","")
    mobile = (agent.get("phone_mobile") or "").replace(" ", "")
    office = (agent.get("phone_office") or "").replace(" ", "")
    emails = [e.strip() for e in (agent.get("emails") or "").split(",") if e.strip()]

    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{name};;;;",
        f"FN:{name}",
    ]
    if mobile: lines.append(f"TEL;TYPE=CELL:{mobile}")
    if office: lines.append(f"TEL;TYPE=WORK:{office}")
    for e in emails:
        lines.append(f"EMAIL;TYPE=INTERNET:{e}")
    lines.append("END:VCARD")
    data = "\r\n".join(lines).encode("utf-8")

    return send_file(BytesIO(data), mimetype="text/vcard", download_name=f"{slug}.vcf")

@app.get("/qr/<slug>.png")
def qr_png(slug):
    slug = normalize_slug(slug)
    agent = DB.get(slug)
    if not agent:
        return render_template("404.html"), 404

    base = BASE_URL or request.host_url.rstrip("/")
    url = f"{base}/{slug}"

    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# -----------------------------------------------------------------------------
# Errori
# -----------------------------------------------------------------------------
@app.errorhandler(404)
def err404(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def err500(e):
    # pagina bianca default è brutta: mostriamo 500 elegante
    return render_template("500.html") if Path("templates/500.html").exists() else ("Internal Server Error", 500)


# -----------------------------------------------------------------------------
# Run (locale)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Per debug locale
    app.run(host="0.0.0.0", port=5000, debug=True)

