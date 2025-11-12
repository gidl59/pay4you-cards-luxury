import os
import sqlite3
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, send_file, abort, jsonify
)
from io import BytesIO
import qrcode
from PIL import Image
from urllib.parse import urljoin

# --------------------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------------------
def read_secret_key():
    # Preferisci file segreto se presente (Render -> Secret Files: SECRET_KEY)
    secret_path = "/etc/secrets/SECRET_KEY"
    if os.path.isfile(secret_path):
        with open(secret_path, "rb") as f:
            return f.read()
    # Altrimenti prendi APP_SECRET dalle env o fallback d’emergenza
    return (os.getenv("APP_SECRET") or "dev-secret-change-me").encode()

app = Flask(__name__)
app.secret_key = read_secret_key()

BASE_URL = os.getenv("BASE_URL", "").strip().rstrip("/")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()

# Dove salviamo il DB (scrivibile su Render): /tmp
DB_PATH = "/tmp/pay4you_cards.db"

# --------------------------------------------------------------------------------------
# DB minimale (sqlite3 “puro”, niente flask_sqlalchemy)
# --------------------------------------------------------------------------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            name TEXT,
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
            created_at TEXT
        );
    """)
    conn.commit()
    conn.close()

init_db()

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def is_admin():
    return bool(session.get("admin"))

def require_admin():
    if not is_admin():
        return redirect(url_for("login"))

def one_agent(slug):
    c = db().execute("SELECT * FROM agents WHERE slug = ?", (slug,))
    row = c.fetchone()
    c.connection.close()
    return row

def all_agents():
    c = db().execute("SELECT * FROM agents ORDER BY id DESC")
    rows = c.fetchall()
    c.connection.close()
    return rows

def save_agent(data, for_update=False):
    conn = db()
    fields = [
        "slug", "name", "company", "role", "bio",
        "phone_mobile", "phone_office", "emails", "websites",
        "facebook", "instagram", "linkedin", "tiktok", "telegram", "whatsapp",
        "pec", "piva", "sdi", "addresses"
    ]
    vals = [data.get(f, "").strip() for f in fields]

    if for_update:
        # update by slug
        set_clause = ", ".join([f"{f} = ?" for f in fields if f != "slug"])
        update_vals = [data.get(f, "").strip() for f in fields if f != "slug"]
        update_vals.append(data.get("slug","").strip())
        conn.execute(f"UPDATE agents SET {set_clause} WHERE slug = ?", update_vals)
    else:
        conn.execute("""
            INSERT INTO agents (
                slug, name, company, role, bio,
                phone_mobile, phone_office, emails, websites,
                facebook, instagram, linkedin, tiktok, telegram, whatsapp,
                pec, piva, sdi, addresses, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, vals + [datetime.utcnow().isoformat()])
    conn.commit()
    conn.close()

def delete_agent(slug):
    conn = db()
    conn.execute("DELETE FROM agents WHERE slug = ?", (slug,))
    conn.commit()
    conn.close()

def card_url(slug):
    # URL assoluto alla card pubblica
    if BASE_URL:
        return f"{BASE_URL}/{slug}"
    # fallback locale
    return url_for("public_card", slug=slug, _external=True)

# --------------------------------------------------------------------------------------
# Rotte pubbliche
# --------------------------------------------------------------------------------------
@app.get("/health")
def health():
    return "OK", 200

# Alias per soddisfare i template che puntano a 'home' (es. 404.html)
@app.get("/")
def home():
    return redirect(url_for("login"))

# Card pubblica: /<slug>
@app.get("/<slug>")
def public_card(slug):
    agent = one_agent(slug)
    if not agent:
        return render_template("404.html"), 404
    return render_template("card.html", agent=agent)

# QR dinamico PNG: /qr/<slug>.png
@app.get("/qr/<slug>.png")
def qr_png(slug):
    if not one_agent(slug):
        abort(404)
    target = card_url(slug)
    img = qrcode.make(target)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png",
                     download_name=f"{slug}.png")

# vCard: /vcard/<slug>.vcf
@app.get("/vcard/<slug>.vcf")
def vcard(slug):
    agent = one_agent(slug)
    if not agent:
        abort(404)

    name = agent["name"] or ""
    fn = name.replace("\n", " ")
    tel1 = (agent["phone_mobile"] or "").replace(" ", "")
    tel2 = (agent["phone_office"] or "").replace(" ", "")
    emails = (agent["emails"] or "").split(",")
    org = agent["company"] or ""
    title = agent["role"] or ""
    url_primary = (agent["websites"] or "").split(",")[0].strip()
    adr = (agent["addresses"] or "").split("\n")[0].strip()

    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN:{fn}",
        f"ORG:{org}",
        f"TITLE:{title}",
    ]
    if tel1:
        lines.append(f"TEL;TYPE=CELL:{tel1}")
    if tel2:
        lines.append(f"TEL;TYPE=WORK:{tel2}")
    for e in emails:
        e = e.strip()
        if e:
            lines.append(f"EMAIL;TYPE=INTERNET:{e}")
    if url_primary:
        lines.append(f"URL:{url_primary}")
    if adr:
        lines.append(f"ADR;TYPE=WORK:;;{adr};;;;")
    lines.append("END:VCARD")

    data = "\r\n".join(lines).encode("utf-8")
    return send_file(
        BytesIO(data),
        mimetype="text/vcard",
        download_name=f"{slug}.vcf"
    )

# --------------------------------------------------------------------------------------
# Login / Logout
# --------------------------------------------------------------------------------------
@app.get("/login")
def login():
    # Pagina di login (solo password)
    if is_admin():
        return redirect(url_for("admin_home"))
    return render_template("login.html")

@app.post("/login")
def login_post():
    pwd = (request.form.get("password") or "").strip()
    if not ADMIN_PASSWORD:
        # se non configurata, blocchiamo l’accesso
        return render_template("login.html", error="ADMIN_PASSWORD non configurata su Render.")
    if pwd == ADMIN_PASSWORD:
        session["admin"] = True
        return redirect(url_for("admin_home"))
    return render_template("login.html", error="Password errata.")

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --------------------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------------------
@app.get("/admin")
def admin_home():
    if not is_admin():
        return redirect(url_for("login"))
    agents = all_agents()
    return render_template("admin_list.html", agents=agents)

@app.get("/admin/new")
def admin_new():
    if not is_admin():
        return redirect(url_for("login"))
    return render_template("agent_form.html", agent=None)

@app.post("/admin/new")
def admin_new_post():
    if not is_admin():
        return redirect(url_for("login"))
    data = {k: (request.form.get(k) or "") for k in request.form.keys()}
    # controllo slug
    slug = (data.get("slug") or "").strip()
    if not slug:
        return render_template("agent_form.html", agent=data, error="Slug obbligatorio.")
    if one_agent(slug):
        return render_template("agent_form.html", agent=data, error="Slug già esistente.")
    save_agent(data, for_update=False)
    return redirect(url_for("admin_home"))

@app.get("/admin/<slug>/edit")
def admin_edit(slug):
    if not is_admin():
        return redirect(url_for("login"))
    agent = one_agent(slug)
    if not agent:
        return render_template("404.html"), 404
    return render_template("agent_form.html", agent=agent)

@app.post("/admin/<slug>/edit")
def admin_edit_post(slug):
    if not is_admin():
        return redirect(url_for("login"))
    data = {k: (request.form.get(k) or "") for k in request.form.keys()}
    data["slug"] = slug  # non permettiamo cambio slug dalla form
    if not one_agent(slug):
        return render_template("agent_form.html", agent=data, error="Agente non trovato.")
    save_agent(data, for_update=True)
    return redirect(url_for("admin_home"))

@app.post("/admin/<slug>/delete")
def admin_delete(slug):
    if not is_admin():
        return redirect(url_for("login"))
    if not one_agent(slug):
        return render_template("404.html"), 404
    delete_agent(slug)
    return redirect(url_for("admin_home"))

# --------------------------------------------------------------------------------------
# Error handlers
# --------------------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    # Usa il tuo 404.html
    return render_template("404.html"), 404

# --------------------------------------------------------------------------------------
# Avvio locale
# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    # Avvio dev
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)

