import os
import json
import sqlite3
from io import BytesIO
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, abort, send_file, flash
)

import qrcode

# ------------------------------------------------------------------------------
# Config base
# ------------------------------------------------------------------------------
app = Flask(__name__)

# segreta per la sessione (se non c'è nelle env, ne genera una semplice)
app.secret_key = os.environ.get("SECRET_KEY", "pay4you-secret")

# Base URL pubblico (quello di Render, senza / finale)
BASE_URL = os.environ.get("BASE_URL", "http://localhost:10000").rstrip("/")

# Credenziali admin (env)
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin")

# Cartella upload locale
UPLOAD_DIR = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ------------------------------------------------------------------------------
# DB helpers (SQLite)
# ------------------------------------------------------------------------------
def get_db():
    if not hasattr(app, "_db"):
        db_path = os.path.join(app.root_path, "db.sqlite")
        app._db = sqlite3.connect(db_path, check_same_thread=False)
        app._db.row_factory = sqlite3.Row
    return app._db

def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            company TEXT,
            role TEXT,
            bio TEXT,

            phone_mobile TEXT,
            phone_office TEXT,

            emails TEXT,
            websites TEXT,

            facebook TEXT,
            instagram TEXT,
            linkedin TEXT,
            tiktok TEXT,
            telegram TEXT,
            whatsapp TEXT,

            pec TEXT,
            piva TEXT,
            sdi TEXT,

            addresses TEXT,

            photo_url TEXT,
            pdf1_url TEXT,
            pdf2_url TEXT,

            gallery_json TEXT,

            created_at TEXT,
            updated_at TEXT
        );
        """
    )
    db.commit()

@app.before_first_request
def _ensure_db():
    init_db()

# ------------------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------------------
def is_admin():
    return bool(session.get("admin"))

def require_admin():
    if not is_admin():
        return redirect(url_for("login"))

def now_iso():
    return datetime.utcnow().isoformat()

def find_agent_by_slug(slug: str):
    """Trova agente ignorando maiuscole/minuscole."""
    s = (slug or "").strip()
    db = get_db()
    row = db.execute("SELECT * FROM agents WHERE slug = ?", (s,)).fetchone()
    if not row:
        row = db.execute("SELECT * FROM agents WHERE lower(slug) = lower(?)", (s,)).fetchone()
    return row

def save_upload(fs_storage, subdir=""):
    """Salva un file di Flask `request.files[...]` e ritorna la URL statica."""
    if not fs_storage or not fs_storage.filename:
        return None
    name = fs_storage.filename.strip().replace(" ", "_")
    if subdir:
        target_dir = os.path.join(UPLOAD_DIR, subdir)
    else:
        target_dir = UPLOAD_DIR
    os.makedirs(target_dir, exist_ok=True)
    # timestamp nel nome per evitare collisioni
    base, ext = os.path.splitext(name)
    safe_name = f"{base}_{int(datetime.utcnow().timestamp())}{ext}"
    abs_path = os.path.join(target_dir, safe_name)
    fs_storage.save(abs_path)
    # URL statica
    rel_path = os.path.relpath(abs_path, os.path.join(app.root_path, "static"))
    return url_for("static", filename=rel_path).replace("\\", "/")

def make_qr_png(url: str) -> BytesIO:
    """Genera PNG del QR come BytesIO."""
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ------------------------------------------------------------------------------
# Routes pubbliche
# ------------------------------------------------------------------------------
@app.get("/")
def home():
    # Semplice redirect alla dashboard se loggato, al login altrimenti
    if is_admin():
        return redirect(url_for("admin_home"))
    return redirect(url_for("login"))

@app.get("/health")
def health():
    return "ok", 200

@app.get("/<slug>")
def public_card(slug):
    agent = find_agent_by_slug(slug)
    if not agent:
        return render_template("404.html"), 404
    # gallery come lista
    gallery = []
    if agent["gallery_json"]:
        try:
            gallery = json.loads(agent["gallery_json"])
        except Exception:
            gallery = []
    return render_template("card.html", agent=agent, gallery=gallery, BASE_URL=BASE_URL)

# QR personale (accetta /qr/<slug> e /qr/<slug>.png)
@app.get("/qr/<slug>")
@app.get("/qr/<slug>.png")
def qr_personal(slug):
    agent = find_agent_by_slug(slug)
    if not agent:
        abort(404)
    url = f"{BASE_URL}/{agent['slug']}"
    png = make_qr_png(url)
    # Restituisce sempre PNG
    return send_file(png, mimetype="image/png", download_name=f"{agent['slug']}.png")

# vCard
@app.get("/<slug>.vcf")
def vcard(slug):
    agent = find_agent_by_slug(slug)
    if not agent:
        abort(404)

    name = agent["name"] or ""
    tel_m = agent["phone_mobile"] or ""
    tel_o = agent["phone_office"] or ""
    emails = (agent["emails"] or "").split(",")
    email1 = (emails[0].strip() if emails and emails[0].strip() else "")
    org = agent["company"] or ""
    title = agent["role"] or ""
    # prendi solo il primo indirizzo (se serve)
    address = ""
    if agent["addresses"]:
        lines = [l.strip() for l in agent["addresses"].splitlines() if l.strip()]
        address = lines[0] if lines else ""

    vcf = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{name};;;;",
        f"FN:{name}",
        f"ORG:{org}",
        f"TITLE:{title}",
    ]
    if tel_m:
        vcf.append(f"TEL;TYPE=CELL:{tel_m}")
    if tel_o:
        vcf.append(f"TEL;TYPE=WORK:{tel_o}")
    if email1:
        vcf.append(f"EMAIL;TYPE=INTERNET:{email1}")
    if address:
        vcf.append(f"ADR;TYPE=WORK:;;{address};;;;")
    vcf.extend(["END:VCARD", ""])

    data = "\r\n".join(vcf).encode("utf-8")
    return send_file(
        BytesIO(data),
        mimetype="text/vcard",
        as_attachment=True,
        download_name=f"{agent['slug']}.vcf"
    )

# ------------------------------------------------------------------------------
# Auth admin
# ------------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        if u == ADMIN_USER and p == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin_home"))
        flash("Credenziali non valide", "error")
    return render_template("login.html")

@app.get("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("login"))

# ------------------------------------------------------------------------------
# Admin CRUD
# ------------------------------------------------------------------------------
@app.get("/admin")
def admin_home():
    if not is_admin():
        return require_admin()
    db = get_db()
    rows = db.execute("SELECT * FROM agents ORDER BY name COLLATE NOCASE").fetchall()
    return render_template("admin_list.html", agents=rows)

@app.route("/admin/new", methods=["GET", "POST"])
def admin_new():
    if not is_admin():
        return require_admin()
    if request.method == "POST":
        return _save_agent()
    return render_template("agent_form.html", agent=None)

@app.route("/admin/<slug>/edit", methods=["GET", "POST"])
def admin_edit(slug):
    if not is_admin():
        return require_admin()
    agent = find_agent_by_slug(slug)
    if not agent:
        return render_template("404.html"), 404
    if request.method == "POST":
        return _save_agent(existing=agent)
    return render_template("agent_form.html", agent=agent)

@app.post("/admin/<slug>/delete")
def admin_delete(slug):
    if not is_admin():
        return require_admin()
    db = get_db()
    db.execute("DELETE FROM agents WHERE slug = ?", (slug,))
    db.commit()
    return redirect(url_for("admin_home"))

def _save_agent(existing=None):
    """Crea/aggiorna un agente dai dati del form + upload media."""
    db = get_db()

    slug = (request.form.get("slug") or "").strip().replace(" ", "-")
    # se vuoi forzare minuscolo:
    # slug = slug.lower()

    name = (request.form.get("name") or "").strip()
    company = (request.form.get("company") or "").strip()
    role = (request.form.get("role") or "").strip()
    bio = (request.form.get("bio") or "").strip()

    phone_mobile = (request.form.get("phone_mobile") or "").strip()
    phone_office = (request.form.get("phone_office") or "").strip()

    emails = (request.form.get("emails") or "").strip()
    websites = (request.form.get("websites") or "").strip()

    facebook = (request.form.get("facebook") or "").strip()
    instagram = (request.form.get("instagram") or "").strip()
    linkedin = (request.form.get("linkedin") or "").strip()
    tiktok = (request.form.get("tiktok") or "").strip()
    telegram = (request.form.get("telegram") or "").strip()
    whatsapp = (request.form.get("whatsapp") or "").strip()

    pec = (request.form.get("pec") or "").strip()
    piva = (request.form.get("piva") or "").strip()
    sdi = (request.form.get("sdi") or "").strip()

    addresses = (request.form.get("addresses") or "").strip()

    # Upload media (opzionali)
    photo_url = save_upload(request.files.get("photo"), "photos") or (existing["photo_url"] if existing else None)
    pdf1_url = save_upload(request.files.get("pdf1"), "pdf") or (existing["pdf1_url"] if existing else None)
    pdf2_url = save_upload(request.files.get("pdf2"), "pdf") or (existing["pdf2_url"] if existing else None)

    # Galleria multipla
    gallery_urls = []
    if existing and existing["gallery_json"]:
        try:
            gallery_urls = json.loads(existing["gallery_json"]) or []
        except Exception:
            gallery_urls = []

    if "gallery" in request.files:
        for fs in request.files.getlist("gallery"):
            u = save_upload(fs, "gallery")
            if u:
                gallery_urls.append(u)

    if existing:
        db.execute(
            """
            UPDATE agents SET
                slug=?, name=?, company=?, role=?, bio=?,
                phone_mobile=?, phone_office=?,
                emails=?, websites=?,
                facebook=?, instagram=?, linkedin=?, tiktok=?, telegram=?, whatsapp=?,
                pec=?, piva=?, sdi=?,
                addresses=?,
                photo_url=?, pdf1_url=?, pdf2_url=?,
                gallery_json=?,
                updated_at=?
            WHERE id=?
            """,
            (
                slug, name, company, role, bio,
                phone_mobile, phone_office,
                emails, websites,
                facebook, instagram, linkedin, tiktok, telegram, whatsapp,
                pec, piva, sdi,
                addresses,
                photo_url, pdf1_url, pdf2_url,
                json.dumps(gallery_urls),
                now_iso(),
                existing["id"],
            ),
        )
    else:
        db.execute(
            """
            INSERT INTO agents (
                slug, name, company, role, bio,
                phone_mobile, phone_office,
                emails, websites,
                facebook, instagram, linkedin, tiktok, telegram, whatsapp,
                pec, piva, sdi,
                addresses,
                photo_url, pdf1_url, pdf2_url,
                gallery_json,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,
                      ?,?,
                      ?,?,
                      ?,?,?,?, ?,?,
                      ?,?,?,
                      ?,
                      ?,?,?,
                      ?,?,?)
            """,
            (
                slug, name, company, role, bio,
                phone_mobile, phone_office,
                emails, websites,
                facebook, instagram, linkedin, tiktok, telegram, whatsapp,
                pec, piva, sdi,
                addresses,
                photo_url, pdf1_url, pdf2_url,
                json.dumps(gallery_urls),
                now_iso(), now_iso(),
            ),
        )

    db.commit()
    return redirect(url_for("admin_home"))

# ------------------------------------------------------------------------------
# Errori
# ------------------------------------------------------------------------------
@app.errorhandler(404)
def _404(e):
    return render_template("404.html"), 404

# ------------------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Avvio dev
    app.run(host="0.0.0.0", port=10000, debug=True)
