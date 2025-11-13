import os
import sqlite3
from contextlib import closing
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_file,
    abort,
    Response,
)

import io
import qrcode

# -----------------------------------------------------------------------------
# Configurazione base
# -----------------------------------------------------------------------------

app = Flask(__name__)  # usa la cartella "static" di default

# Secret key per la sessione
app.secret_key = (
    os.getenv("APP_SECRET")
    or os.getenv("SECRET_KEY")
    or "dev-secret-change-me"
)

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "test")

DB_PATH = os.path.join(os.path.dirname(__file__), "agents.db")


# -----------------------------------------------------------------------------
# Database (SQLite)
# -----------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_db()) as db:
        db.execute(
            """
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
                photo_url TEXT,
                gallery_urls TEXT,
                pdf1_url TEXT,
                pdf2_url TEXT
            )
            """
        )
        db.commit()


@app.before_first_request
def _startup():
    init_db()


# -----------------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------------

def require_admin(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return wrapper


def load_agent_by_slug(slug: str):
    db = get_db()
    cur = db.execute("SELECT * FROM agents WHERE slug = ?", (slug,))
    row = cur.fetchone()
    db.close()
    return row


def parse_addresses(text: str):
    if not text:
        return []
    return [a.strip() for a in text.splitlines() if a.strip()]


def parse_list(text: str, separator=","):
    if not text:
        return []
    return [x.strip() for x in text.split(separator) if x.strip()]


# -----------------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------------

@app.route("/health")
def health():
    return "OK", 200


# -----------------------------------------------------------------------------
# Login / Logout
# -----------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pwd = request.form.get("password", "")
        # solo password, niente utente
        if pwd == ADMIN_PASSWORD:
            session["admin"] = True
            flash("Accesso effettuato.", "success")
            return redirect(url_for("admin_home"))
        flash("Password errata.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -----------------------------------------------------------------------------
# Admin dashboard
# -----------------------------------------------------------------------------

@app.route("/admin")
@require_admin
def admin_home():
    db = get_db()
    cur = db.execute("SELECT * FROM agents ORDER BY name COLLATE NOCASE")
    agents = cur.fetchall()
    db.close()
    return render_template("admin_list.html", agents=agents)


@app.route("/admin/new", methods=["GET", "POST"])
@require_admin
def admin_new():
    if request.method == "POST":
        return save_agent()
    return render_template("agent_form.html", agent=None)


@app.route("/admin/<slug>/edit", methods=["GET", "POST"])
@require_admin
def admin_edit(slug):
    agent = load_agent_by_slug(slug)
    if not agent:
        flash("Agente non trovato.", "error")
        return redirect(url_for("admin_home"))

    if request.method == "POST":
        return save_agent(existing_slug=slug)

    # addresses va mostrato come testo con a capo
    addresses = ""
    if agent["addresses"]:
        for line in parse_addresses(agent["addresses"]):
            addresses += line + "\n"

    agent = dict(agent)
    agent["addresses"] = addresses
    return render_template("agent_form.html", agent=agent)


@app.route("/admin/<slug>/delete", methods=["POST"])
@require_admin
def admin_delete(slug):
    db = get_db()
    db.execute("DELETE FROM agents WHERE slug = ?", (slug,))
    db.commit()
    db.close()
    flash("Agente eliminato.", "success")
    return redirect(url_for("admin_home"))


def save_agent(existing_slug: str | None = None):
    """Gestisce sia creazione che modifica."""

    form = request.form
    slug = (form.get("slug") or "").strip().lower()

    if not slug:
        flash("Lo slug è obbligatorio.", "error")
        return redirect(request.url)

    # dati base
    data = {
        "slug": slug,
        "name": form.get("name", "").strip(),
        "company": form.get("company", "").strip(),
        "role": form.get("role", "").strip(),
        "bio": form.get("bio", "").strip(),
        "phone_mobile": form.get("phone_mobile", "").strip(),
        "phone_office": form.get("phone_office", "").strip(),
        "emails": form.get("emails", "").strip(),
        "websites": form.get("websites", "").strip(),
        "facebook": form.get("facebook", "").strip(),
        "instagram": form.get("instagram", "").strip(),
        "linkedin": form.get("linkedin", "").strip(),
        "tiktok": form.get("tiktok", "").strip(),
        "telegram": form.get("telegram", "").strip(),
        "whatsapp": form.get("whatsapp", "").strip(),
        "pec": form.get("pec", "").strip(),
        "piva": form.get("piva", "").strip(),
        "sdi": form.get("sdi", "").strip(),
        "addresses": form.get("addresses", "").strip(),
        "photo_url": form.get("photo_url", "").strip(),
        "gallery_urls": form.get("gallery_urls", "").strip(),
        "pdf1_url": form.get("pdf1_url", "").strip(),
        "pdf2_url": form.get("pdf2_url", "").strip(),
    }

    db = get_db()

    if existing_slug:
        # update
        db.execute(
            """
            UPDATE agents SET
                slug=:slug,
                name=:name,
                company=:company,
                role=:role,
                bio=:bio,
                phone_mobile=:phone_mobile,
                phone_office=:phone_office,
                emails=:emails,
                websites=:websites,
                facebook=:facebook,
                instagram=:instagram,
                linkedin=:linkedin,
                tiktok=:tiktok,
                telegram=:telegram,
                whatsapp=:whatsapp,
                pec=:pec,
                piva=:piva,
                sdi=:sdi,
                addresses=:addresses,
                photo_url=:photo_url,
                gallery_urls=:gallery_urls,
                pdf1_url=:pdf1_url,
                pdf2_url=:pdf2_url
            WHERE slug=:orig_slug
            """,
            {**data, "orig_slug": existing_slug},
        )
    else:
        # insert
        try:
            db.execute(
                """
                INSERT INTO agents (
                    slug, name, company, role, bio,
                    phone_mobile, phone_office,
                    emails, websites,
                    facebook, instagram, linkedin, tiktok, telegram, whatsapp,
                    pec, piva, sdi,
                    addresses,
                    photo_url, gallery_urls,
                    pdf1_url, pdf2_url
                ) VALUES (
                    :slug, :name, :company, :role, :bio,
                    :phone_mobile, :phone_office,
                    :emails, :websites,
                    :facebook, :instagram, :linkedin, :tiktok, :telegram, :whatsapp,
                    :pec, :piva, :sdi,
                    :addresses,
                    :photo_url, :gallery_urls,
                    :pdf1_url, :pdf2_url
                )
                """,
                data,
            )
        except sqlite3.IntegrityError:
            db.close()
            flash("Slug già esistente, scegline un altro.", "error")
            return redirect(request.url)

    db.commit()
    db.close()
    flash("Dati salvati.", "success")
    return redirect(url_for("admin_home"))


# -----------------------------------------------------------------------------
# Card pubblica
# -----------------------------------------------------------------------------

@app.route("/")
def root_redirect():
    # se sei loggato vai alla dashboard, altrimenti al login
    if session.get("admin"):
        return redirect(url_for("admin_home"))
    return redirect(url_for("login"))


@app.route("/<slug>")
def public_card(slug):
    agent = load_agent_by_slug(slug)
    if not agent:
        return render_template("404.html"), 404

    agent = dict(agent)

    # liste
    agent["emails_list"] = parse_list(agent.get("emails"))
    agent["websites_list"] = parse_list(agent.get("websites"))
    agent["addresses_list"] = parse_addresses(agent.get("addresses"))
    agent["gallery_list"] = parse_list(agent.get("gallery_urls"), separator="\n")

    return render_template("card.html", agent=agent)


# -----------------------------------------------------------------------------
# QR Code & vCard
# -----------------------------------------------------------------------------

@app.route("/qr/<slug>.png")
def qr_png(slug):
    agent = load_agent_by_slug(slug)
    if not agent:
        abort(404)

    url = f"{os.getenv('BASE_URL', '').rstrip('/')}/{slug}"
    if not url.startswith("http"):
        # fallback se BASE_URL non è impostato correttamente
        url = request.url_root.rstrip("/") + "/" + slug

    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/vcard/<slug>.vcf")
def vcard(slug):
    agent = load_agent_by_slug(slug)
    if not agent:
        abort(404)

    a = agent
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{a['name']};",
        f"FN:{a['name']}",
    ]

    if a["company"]:
        lines.append(f"ORG:{a['company']}")
    if a["role"]:
        lines.append(f"TITLE:{a['role']}")

    if a["phone_mobile"]:
        lines.append(f"TEL;TYPE=CELL:{a['phone_mobile']}")
    if a["phone_office"]:
        lines.append(f"TEL;TYPE=WORK:{a['phone_office']}")

    if a["emails"]:
        for mail in parse_list(a["emails"]):
            lines.append(f"EMAIL;TYPE=INTERNET:{mail}")

    if a["websites"]:
        for site in parse_list(a["websites"]):
            lines.append(f"URL:{site}")

    # primo indirizzo, se presente
    addrs = parse_addresses(a["addresses"])
    if addrs:
        lines.append(f"ADR;TYPE=WORK:;;{addrs[0]};;;;")

    lines.append("END:VCARD")
    vcf = "\r\n".join(lines)

    return Response(
        vcf,
        mimetype="text/vcard",
        headers={"Content-Disposition": f'attachment; filename="{slug}.vcf"'},
    )


# -----------------------------------------------------------------------------
# Errori
# -----------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


# -----------------------------------------------------------------------------
# Avvio locale
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)

