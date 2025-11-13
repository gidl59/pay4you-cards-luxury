import os
import io
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    Response,
)
from flask_sqlalchemy import SQLAlchemy
import qrcode

# -----------------------------------------------------------------------------
# Configurazione base
# -----------------------------------------------------------------------------
app = Flask(__name__)

# DB: usa DATABASE_URL se esiste (Postgres su Render) altrimenti sqlite locale
database_url = os.environ.get("DATABASE_URL", "sqlite:///agents.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.secret_key = os.environ.get("APP_SECRET", "dev-secret")

db = SQLAlchemy(app)

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "test")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")

# -----------------------------------------------------------------------------
# Modello
# -----------------------------------------------------------------------------
class Agent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)

    company = db.Column(db.String(120))
    role = db.Column(db.String(120))
    bio = db.Column(db.Text)

    phone_mobile = db.Column(db.String(50))
    phone_office = db.Column(db.String(50))
    emails = db.Column(db.Text)
    websites = db.Column(db.Text)

    facebook = db.Column(db.Text)
    instagram = db.Column(db.Text)
    linkedin = db.Column(db.Text)
    tiktok = db.Column(db.Text)
    telegram = db.Column(db.Text)
    whatsapp = db.Column(db.Text)

    pec = db.Column(db.String(120))
    piva = db.Column(db.String(50))
    sdi = db.Column(db.String(50))
    addresses = db.Column(db.Text)

    photo_url = db.Column(db.Text)
    pdf1_url = db.Column(db.Text)
    pdf2_url = db.Column(db.Text)
    gallery_urls = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


with app.app_context():
    db.create_all()


# -----------------------------------------------------------------------------
# Util
# -----------------------------------------------------------------------------
def is_admin():
    return session.get("admin") == ADMIN_USER


def fill_agent_from_form(agent: Agent):
    f = request.form

    agent.slug = (f.get("slug") or agent.slug or "").strip().lower()
    agent.name = (f.get("name") or "").strip()

    agent.company = (f.get("company") or "").strip() or None
    agent.role = (f.get("role") or "").strip() or None
    agent.bio = (f.get("bio") or "").strip() or None

    agent.phone_mobile = (f.get("phone_mobile") or "").strip() or None
    agent.phone_office = (f.get("phone_office") or "").strip() or None

    agent.emails = (f.get("emails") or "").strip() or None
    agent.websites = (f.get("websites") or "").strip() or None

    agent.facebook = (f.get("facebook") or "").strip() or None
    agent.instagram = (f.get("instagram") or "").strip() or None
    agent.linkedin = (f.get("linkedin") or "").strip() or None
    agent.tiktok = (f.get("tiktok") or "").strip() or None
    agent.telegram = (f.get("telegram") or "").strip() or None
    agent.whatsapp = (f.get("whatsapp") or "").strip() or None

    agent.pec = (f.get("pec") or "").strip() or None
    agent.piva = (f.get("piva") or "").strip() or None
    agent.sdi = (f.get("sdi") or "").strip() or None
    agent.addresses = (f.get("addresses") or "").strip() or None

    agent.photo_url = (f.get("photo_url") or "").strip() or None
    agent.pdf1_url = (f.get("pdf1_url") or "").strip() or None
    agent.pdf2_url = (f.get("pdf2_url") or "").strip() or None
    agent.gallery_urls = (f.get("gallery_urls") or "").strip() or None


# -----------------------------------------------------------------------------
# Healthcheck
# -----------------------------------------------------------------------------
@app.route("/health")
def health():
    return "ok", 200


# -----------------------------------------------------------------------------
# Autenticazione
# -----------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["admin"] = ADMIN_USER
            return redirect(url_for("admin_home"))
        else:
            error = "Password errata."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -----------------------------------------------------------------------------
# Dashboard admin
# -----------------------------------------------------------------------------
@app.route("/admin")
def admin_home():
    if not is_admin():
        return redirect(url_for("login"))

    agents = Agent.query.order_by(Agent.name.asc()).all()
    return render_template("admin_list.html", agents=agents, base_url=BASE_URL)


@app.route("/admin/new", methods=["GET", "POST"])
def admin_new():
    if not is_admin():
        return redirect(url_for("login"))

    error = None
    if request.method == "POST":
        slug = (request.form.get("slug") or "").strip().lower()
        if not slug:
            error = "Slug obbligatorio."
        elif Agent.query.filter_by(slug=slug).first():
            error = "Slug già esistente."
        else:
            agent = Agent(slug=slug)
            fill_agent_from_form(agent)
            db.session.add(agent)
            db.session.commit()
            return redirect(url_for("admin_home"))

    return render_template("agent_form.html", agent=None, error=error)


@app.route("/admin/<slug>/edit", methods=["GET", "POST"])
def admin_edit(slug):
    if not is_admin():
        return redirect(url_for("login"))

    agent = Agent.query.filter_by(slug=slug).first_or_404()
    error = None

    if request.method == "POST":
        fill_agent_from_form(agent)
        db.session.commit()
        return redirect(url_for("admin_home"))

    return render_template("agent_form.html", agent=agent, error=error)


@app.route("/admin/<slug>/delete", methods=["POST"])
def admin_delete(slug):
    if not is_admin():
        return redirect(url_for("login"))

    agent = Agent.query.filter_by(slug=slug).first_or_404()
    db.session.delete(agent)
    db.session.commit()
    return redirect(url_for("admin_home"))


# -----------------------------------------------------------------------------
# QR e vCard
# -----------------------------------------------------------------------------
@app.route("/qr/<slug>.png")
def qr_png(slug):
    agent = Agent.query.filter_by(slug=slug).first_or_404()
    url = f"{BASE_URL}/{agent.slug}"

    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return Response(buf.getvalue(), mimetype="image/png")


@app.route("/vcard/<slug>.vcf")
def vcard(slug):
    a = Agent.query.filter_by(slug=slug).first_or_404()

    mobile = (a.phone_mobile or "").strip()
    office = (a.phone_office or "").strip()

    email = ""
    if a.emails:
        email = a.emails.split(",")[0].strip()

    website = ""
    if a.websites:
        website = a.websites.split(",")[0].strip()
        if website and not website.startswith("http"):
            website = "https://" + website

    vcf = f"""BEGIN:VCARD
VERSION:3.0
FN:{a.name}
ORG:{a.company or 'Pay4You'}
TITLE:{a.role or ''}
TEL;TYPE=CELL:{mobile}
TEL;TYPE=WORK:{office}
EMAIL;TYPE=INTERNET,WORK:{email}
URL:{website}
END:VCARD
"""

    return Response(
        vcf,
        mimetype="text/vcard",
        headers={"Content-Disposition": f'attachment; filename="{a.slug}.vcf"'},
    )


# -----------------------------------------------------------------------------
# Card pubblica
# -----------------------------------------------------------------------------
@app.route("/<slug>")
def public_card(slug):
    agent = Agent.query.filter_by(slug=slug).first()
    if not agent:
        return render_template("404.html"), 404

    # liste pulite per il template
    emails = []
    if agent.emails:
        emails = [e.strip() for e in agent.emails.split(",") if e.strip()]

    websites = []
    if agent.websites:
        websites = [w.strip() for w in agent.websites.split(",") if w.strip()]

    gallery = []
    if agent.gallery_urls:
        raw = (
            agent.gallery_urls.replace("\r", "")
            .replace(";", ",")
            .replace("\n", ",")
        )
        for u in raw.split(","):
            u = u.strip()
            if u:
                gallery.append(u)

    addresses = []
    if agent.addresses:
        addresses = [
            a.strip() for a in agent.addresses.splitlines() if a.strip()
        ]

    return render_template(
        "card.html",
        agent=agent,
        emails=emails,
        websites=websites,
        gallery=gallery,
        addresses=addresses,
    )


# -----------------------------------------------------------------------------
# Errori
# -----------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
