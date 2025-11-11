import os
import sqlite3
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_file, abort
)
import qrcode
import vobject
from io import BytesIO

# -----------------------------------------------------------
# CONFIGURAZIONE BASE
# -----------------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pay4you-secret")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:10000").rstrip("/")

DB_FILE = "data.db"

# -----------------------------------------------------------
# DATABASE
# -----------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_FILE)
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

# ✅ Flask 3.x → niente before_first_request
with app.app_context():
    init_db()

# -----------------------------------------------------------
# LOGIN ADMIN
# -----------------------------------------------------------

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["user"] == ADMIN_USER and request.form["pwd"] == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin_home"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -----------------------------------------------------------
# ADMIN PANEL
# -----------------------------------------------------------

@app.route("/admin")
def admin_home():
    if not session.get("admin"):
        return redirect(url_for("login"))
    conn = get_db()
    agents = conn.execute("SELECT * FROM agents").fetchall()
    return render_template("admin_list.html", agents=agents)

@app.route("/admin/new", methods=["GET", "POST"])
def admin_new():
    if not session.get("admin"):
        return redirect(url_for("login"))
    if request.method == "POST":
        save_agent(request.form)
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
        save_agent(request.form, slug)
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

def save_agent(f, old_slug=None):
    conn = get_db()
    slug = f["slug"].strip()
    data = (
        slug, f["name"], f["company"], f["role"], f["bio"],
        f["phone_mobile"], f["phone_office"], f["emails"], f["websites"],
        f["facebook"], f["instagram"], f["linkedin"], f["tiktok"],
        f["telegram"], f["whatsapp"], f["pec"], f["piva"], f["sdi"],
        f["addresses"]
    )
    if old_slug:
        conn.execute("""
            UPDATE agents SET
            slug=?, name=?, company=?, role=?, bio=?, phone_mobile=?, phone_office=?,
            emails=?, websites=?, facebook=?, instagram=?, linkedin=?, tiktok=?, telegram=?,
            whatsapp=?, pec=?, piva=?, sdi=?, addresses=? WHERE slug=?
        """, data + (old_slug,))
    else:
        conn.execute("""
            INSERT INTO agents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, data)
    conn.commit()

# -----------------------------------------------------------
# CARD PUBBLICA
# -----------------------------------------------------------

@app.route("/<slug>")
def public_card(slug):
    conn = get_db()
    a = conn.execute("SELECT * FROM agents WHERE slug=?", (slug,)).fetchone()
    if not a:
        return render_template("404.html"), 404
    return render_template("card.html", a=a, link=f"{BASE_URL}/{slug}")

# -----------------------------------------------------------
# QR CODE
# -----------------------------------------------------------

@app.route("/qr/<slug>.png")
def qr_png(slug):
    url = f"{BASE_URL}/{slug}"
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

@app.route("/qr/<slug>")
def qr_page(slug):
    return render_template("qr.html", url=f"{BASE_URL}/{slug}")

# -----------------------------------------------------------
# VCARD
# -----------------------------------------------------------

@app.route("/vcard/<slug>.vcf")
def vcard(slug):
    conn = get_db()
    a = conn.execute("SELECT * FROM agents WHERE slug=?", (slug,)).fetchone()
    if not a:
        abort(404)
    card = vobject.vCard()
    card.add('fn').value = a["name"]
    card.add('tel').value = a["phone_mobile"]
    if a["emails"]:
        for e in a["emails"].split(","):
            email = card.add('email')
            email.value = e.strip()
    out = card.serialize()
    return send_file(BytesIO(out.encode()), mimetype="text/vcard", download_name=f"{slug}.vcf")

# -----------------------------------------------------------
# HEALTH CHECK
# -----------------------------------------------------------

@app.route("/health")
def health():
    return "OK"

# -----------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

