import os
import sqlite3
from io import BytesIO
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_file, abort
)
import qrcode

# ------------------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------------------
app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "pay4you-secret")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:10000").rstrip("/")

DB_FILE = os.path.join(os.path.dirname(__file__), "db.sqlite")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin")

# ------------------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            slug TEXT PRIMARY KEY,
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

            addresses TEXT
        )
    """)
    conn.commit()

# Flask 3.x: niente before_first_request → inizializzo qui
with app.app_context():
    init_db()

# ------------------------------------------------------------------------------
# Login / Logout
# ------------------------------------------------------------------------------
@app.route("/")
def home():
    # se sei già loggato vai in admin, altrimenti login
    if session.get("admin"):
        return redirect(url_for("admin_home"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("user") == ADMIN_USER and request.form.get("pwd") == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin_home"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ------------------------------------------------------------------------------
# Admin
# ------------------------------------------------------------------------------
@app.route("/admin")
def admin_home():
    if not session.get("admin"):
        return redirect(url_for("login"))
    conn = get_db()
    agents = conn.execute("SELECT * FROM agents ORDER BY name COLLATE NOCASE").fetchall()
    return render_template("admin_list.html", agents=agents)

@app.route("/admin/new", methods=["GET", "POST"])
def admin_new():
    if not session.get("admin"):
        return redirect(url_for("login"))
    if request.method == "POST":
        _save_agent(request.form)
        return redirect(url_for("admin_home"))
    return render_template("agent_form.html", agent=None)

@app.route("/admin/edit/<slug>", methods=["GET", "POST"])
def admin_edit(slug):
    if not session.get("admin"):
        return redirect(url_for("login"))
    conn = get_db()
    agent = conn.execute("SELECT * FROM agents WHERE slug=?", (slug,)).fetchone()
    if not agent:
        abort(404)
    if request.method == "POST":
        _save_agent(request.form, old_slug=slug)
        return redirect(url_for("admin_home"))
    return render_template("agent_form.html", agent=agent)

@app.route("/admin/delete/<slug>", methods=["POST"])
def admin_delete(slug):
    if not session.get("admin"):
        return redirect(url_for("login"))
    conn = get_db()
    conn.execute("DELETE FROM agents WHERE slug=?", (slug,))
    conn.commit()
    return redirect(url_for("admin_home"))

def _save_agent(form, old_slug=None):
    conn = get_db()
    data = {
        "slug": (form.get("slug") or "").strip(),
        "name": form.get("name"),
        "company": form.get("company"),
        "role": form.get("role"),
        "bio": form.get("bio"),
        "phone_mobile": form.get("phone_mobile"),
        "phone_office": form.get("phone_office"),
        "emails": form.get("emails"),
        "websites": form.get("websites"),
        "facebook": form.get("facebook"),
        "instagram": form.get("instagram"),
        "linkedin": form.get("linkedin"),
        "tiktok": form.get("tiktok"),
        "telegram": form.get("telegram"),
        "whatsapp": form.get("whatsapp"),
        "pec": form.get("pec"),
        "piva": form.get("piva"),
        "sdi": form.get("sdi"),
        "addresses": form.get("addresses"),
    }

    if old_slug:
        conn.execute(
            """
            UPDATE agents SET
              slug=?, name=?, company=?, role=?, bio=?,
              phone_mobile=?, phone_office=?,
              emails=?, websites=?,
              facebook=?, instagram=?, linkedin=?, tiktok=?, telegram=?, whatsapp=?,
              pec=?, piva=?, sdi=?,
              addresses=?
            WHERE slug=?
            """,
            (
                data["slug"], data["name"], data["company"], data["role"], data["bio"],
                data["phone_mobile"], data["phone_office"],
                data["emails"], data["websites"],
                data["facebook"], data["instagram"], data["linkedin"], data["tiktok"], data["telegram"], data["whatsapp"],
                data["pec"], data["piva"], data["sdi"],
                data["addresses"],
                old_slug,
            )
        )
    else:
        conn.execute(
            """
            INSERT INTO agents (
              slug, name, company, role, bio,
              phone_mobile, phone_office,
              emails, websites,
              facebook, instagram, linkedin, tiktok, telegram, whatsapp,
              pec, piva, sdi,
              addresses
            ) VALUES (?,?,?,?,?,
                      ?,?,
                      ?,?,
                      ?,?,?,?, ?,?,
                      ?,?,?,
                      ?)
            """,
            (
                data["slug"], data["name"], data["company"], data["role"], data["bio"],
                data["phone_mobile"], data["phone_office"],
                data["emails"], data["websites"],
                data["facebook"], data["instagram"], data["linkedin"], data["tiktok"], data["telegram"], data["whatsapp"],
                data["pec"], data["piva"], data["sdi"],
                data["addresses"],
            )
        )
    conn.commit()

# ------------------------------------------------------------------------------
# Card pubblica
# ------------------------------------------------------------------------------
@app.route("/<slug>")
def public_card(slug):
    conn = get_db()
    a = conn.execute("SELECT * FROM agents WHERE slug=?", (slug,)).fetchone()
    if not a:
        return render_template("404.html"), 404
    return render_template("card.html", a=a, link=f"{BASE_URL}/{slug}")

# ------------------------------------------------------------------------------
# QR Code
# ------------------------------------------------------------------------------
@app.route("/qr/<slug>.png")
def qr_png(slug):
    url = f"{BASE_URL}/{slug}"
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", download_name=f"{slug}.png")

# alias compatibile se nei template chiami 'qr_personal'
@app.route("/qr/<slug>")
def qr_personal(slug):
    # reindirizza direttamente al PNG
    return redirect(url_for("qr_png", slug=slug))

# ------------------------------------------------------------------------------
# vCard (senza vobject)
# ------------------------------------------------------------------------------
@app.route("/vcard/<slug>.vcf")
def vcard(slug):
    conn = get_db()
    a = conn.execute("SELECT * FROM agents WHERE slug=?", (slug,)).fetchone()
    if not a:
        abort(404)

    name = a["name"] or ""
    org = a["company"] or ""
    title = a["role"] or ""
    tel_m = a["phone_mobile"] or ""
    tel_o = a["phone_office"] or ""
    emails = [e.strip() for e in (a["emails"] or "").split(",") if e.strip()]
    # prendo il primo indirizzo, se presente
    address = ""
    if a["addresses"]:
        lines = [l.strip() for l in a["addresses"].splitlines() if l.strip()]
        if lines:
            address = lines[0]

    # vCard 3.0 minimale
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN:{name}",
        f"N:{name};;;;",
    ]
    if org:
        lines.append(f"ORG:{org}")
    if title:
        lines.append(f"TITLE:{title}")
    if tel_m:
        lines.append(f"TEL;TYPE=CELL:{tel_m}")
    if tel_o:
        lines.append(f"TEL;TYPE=WORK:{tel_o}")
    for e in emails:
        lines.append(f"EMAIL;TYPE=INTERNET:{e}")
    if address:
        lines.append(f"ADR;TYPE=WORK:;;{address};;;;")
    lines.append("END:VCARD")
    vcf = "\r\n".join(lines).encode("utf-8")

    return send_file(
        BytesIO(vcf),
        mimetype="text/vcard",
        download_name=f"{slug}.vcf"
    )

# ------------------------------------------------------------------------------
# Health
# ------------------------------------------------------------------------------
@app.route("/health")
def health():
    return "OK", 200

# ------------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
