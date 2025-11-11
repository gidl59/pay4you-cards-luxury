# app.py  — Pay4You Cards (Luxury)
import os
import io
import json
import secrets
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    send_file, abort, flash
)

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, UniqueConstraint
from sqlalchemy.orm import sessionmaker, declarative_base

import qrcode
from qrcode.image.svg import SvgImage
from PIL import Image

# ---- Firebase (opzionale) ----------------------------------------------------
USE_FIREBASE = bool(os.getenv("FIREBASE_PROJECT_ID"))
gcs_bucket = None
if USE_FIREBASE:
    # inizializzazione lazy più sotto, dopo creazione app
    from google.cloud import storage
    import google.auth
    import google.oauth2.service_account

# ------------------------------------------------------------------------------
# Config / App
# ------------------------------------------------------------------------------

def env_or_default(key, default):
    v = os.getenv(key)
    return v if v is not None and v != "" else default

app = Flask(__name__)

app.secret_key = env_or_default("SECRET_KEY", secrets.token_hex(16))

ADMIN_USER = env_or_default("ADMIN_USER", "admin")
ADMIN_PASS = env_or_default("ADMIN_PASS", "admin123")

BASE_URL   = os.getenv("BASE_URL")  # es. https://pay4you-cards-luxury.onrender.com
DB_URL     = env_or_default("DATABASE_URL", "sqlite:///cards.db")

# ------------------------------------------------------------------------------
# Database (SQLite / Postgres via DATABASE_URL)
# ------------------------------------------------------------------------------

Base = declarative_base()

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True)
    slug = Column(String(120), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    company = Column(String(200))
    role = Column(String(200))
    bio = Column(Text)

    phone_mobile = Column(String(80))
    phone_office = Column(String(80))
    emails = Column(Text)           # separati da virgola
    websites = Column(Text)         # separati da virgola

    facebook = Column(String(300))
    instagram = Column(String(300))
    linkedin = Column(String(300))
    tiktok = Column(String(300))
    telegram = Column(String(300))
    whatsapp = Column(String(300))  # numero o link wa.me

    pec = Column(String(200))
    piva = Column(String(200))
    sdi = Column(String(200))
    addresses = Column(Text)        # uno per riga

    photo_url = Column(String(600))
    pdf1_url = Column(String(600))
    pdf2_url = Column(String(600))
    gallery_json = Column(Text)     # JSON list di URL

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint('slug', name='uq_agent_slug'),)

    @property
    def gallery(self):
        try:
            return json.loads(self.gallery_json) if self.gallery_json else []
        except Exception:
            return []

    @gallery.setter
    def gallery(self, value):
        self.gallery_json = json.dumps(value or [])

# engine + session
engine = create_engine(DB_URL, future=True)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine, future=True)

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def is_admin():
    return bool(session.get("admin"))

def require_admin():
    if not is_admin():
        return redirect(url_for("login"))

def abs_base_url():
    """
    Determina l'URL base assoluto (senza / finale).
    Priorità: env BASE_URL -> request.url_root
    """
    from flask import request as _rq
    if BASE_URL:
        return BASE_URL.rstrip("/")
    # request.url_root termina con /
    return (_rq.url_root or "").rstrip("/")

def parse_list(csv_str):
    return [x.strip() for x in (csv_str or "").split(",") if x.strip()]

def upload_to_storage(file_storage, dest_path):
    """
    Carica un file su Firebase Storage (se configurato) e ritorna l'URL pubblico.
    Se Firebase non è attivo, salva su /tmp e restituisce uno pseudo-URL data: che però
    può essere usato come href diretto. (Semplice e funzionale: i PDF/foto principali
    sono referenziati con URL assoluti quando su Firebase.)
    """
    global gcs_bucket
    if not file_storage or file_storage.filename == "":
        return None

    # Firebase
    if USE_FIREBASE and gcs_bucket:
        blob = gcs_bucket.blob(dest_path)
        blob.upload_from_file(file_storage.stream, content_type=file_storage.mimetype)
        # renda il file pubblico
        blob.make_public()
        return blob.public_url

    # Fallback locale (non “servito”, ma utile per prova: link data:)
    b = file_storage.read()
    import base64
    data_url = f"data:{file_storage.mimetype};base64,{base64.b64encode(b).decode('utf-8')}"
    return data_url

def update_agent_from_form(agent, form, files):
    agent.slug = form.get("slug", "").strip()
    agent.name = form.get("name", "").strip()
    agent.company = form.get("company") or ""
    agent.role = form.get("role") or ""
    agent.bio = form.get("bio") or ""

    agent.phone_mobile = form.get("phone_mobile") or ""
    agent.phone_office = form.get("phone_office") or ""
    agent.emails = form.get("emails") or ""
    agent.websites = form.get("websites") or ""

    agent.facebook = form.get("facebook") or ""
    agent.instagram = form.get("instagram") or ""
    agent.linkedin = form.get("linkedin") or ""
    agent.tiktok = form.get("tiktok") or ""
    agent.telegram = form.get("telegram") or ""
    agent.whatsapp = form.get("whatsapp") or ""

    agent.pec = form.get("pec") or ""
    agent.piva = form.get("piva") or ""
    agent.sdi = form.get("sdi") or ""
    agent.addresses = form.get("addresses") or ""

    # Upload singoli
    photo = files.get("photo")
    if photo and photo.filename:
        agent.photo_url = upload_to_storage(photo, f"agents/{agent.slug}/photo_{int(datetime.utcnow().timestamp())}")

    pdf1 = files.get("pdf1")
    if pdf1 and pdf1.filename:
        agent.pdf1_url = upload_to_storage(pdf1, f"agents/{agent.slug}/doc1_{int(datetime.utcnow().timestamp())}.pdf")

    pdf2 = files.get("pdf2")
    if pdf2 and pdf2.filename:
        agent.pdf2_url = upload_to_storage(pdf2, f"agents/{agent.slug}/doc2_{int(datetime.utcnow().timestamp())}.pdf")

    # Galleria multipla
    gal = files.getlist("gallery")
    gallery_urls = agent.gallery[:]  # esistenti
    for idx, g in enumerate(gal):
        if g and g.filename:
            url = upload_to_storage(g, f"agents/{agent.slug}/gal_{int(datetime.utcnow().timestamp())}_{idx}")
            if url:
                gallery_urls.append(url)
    agent.gallery = gallery_urls

    agent.updated_at = datetime.utcnow()
    return agent

# ------------------------------------------------------------------------------
# Auth / Routing base
# ------------------------------------------------------------------------------

@app.route("/health")
def health():
    return "ok", 200

@app.route("/favicon.ico")
def favicon():
    # Evita errori in log quando il browser chiede la favicon
    return "", 204

@app.route("/")
def home():
    # Se admin loggato → dashboard, altrimenti login
    if is_admin():
        return redirect(url_for("admin_home"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
   @app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        p = request.form.get("password", "")
        if p == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin_home"))
        flash("Password non valida", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("login"))

# ------------------------------------------------------------------------------
# Admin
# ------------------------------------------------------------------------------

@app.route("/admin")
def admin_home():
    if not is_admin():
        return redirect(url_for("login"))
    db = SessionLocal()
    agents = db.query(Agent).order_by(Agent.updated_at.desc()).all()
    db.close()
    return render_template("admin_list.html", agents=agents)

@app.route("/admin/new", methods=["GET", "POST"])
def admin_new():
    if not is_admin():
        return redirect(url_for("login"))
    if request.method == "POST":
        db = SessionLocal()
        a = Agent()
        a = update_agent_from_form(a, request.form, request.files)
        # verifica slug univoco
        if db.query(Agent).filter(Agent.slug == a.slug).first():
            db.close()
            flash("Slug già esistente", "error")
            return render_template("agent_form.html", agent=a)
        db.add(a)
        db.commit()
        db.close()
        return redirect(url_for("admin_home"))
    return render_template("agent_form.html", agent=None)

@app.route("/admin/<slug>/edit", methods=["GET", "POST"])
def admin_edit(slug):
    if not is_admin():
        return redirect(url_for("login"))
    db = SessionLocal()
    a = db.query(Agent).filter(Agent.slug == slug).first()
    if not a:
        db.close()
        return render_template("404.html"), 404
    if request.method == "POST":
        old_slug = a.slug
        a = update_agent_from_form(a, request.form, request.files)
        # se slug cambiato, controlla univocità
        if a.slug != old_slug:
            if db.query(Agent).filter(Agent.slug == a.slug).first():
                flash("Slug già esistente", "error")
                db.rollback()
                db.close()
                return render_template("agent_form.html", agent=a)
        db.commit()
        db.close()
        return redirect(url_for("admin_home"))
    db.close()
    return render_template("agent_form.html", agent=a)

@app.route("/admin/<slug>/delete", methods=["POST"])
def admin_delete(slug):
    if not is_admin():
        return redirect(url_for("login"))
    db = SessionLocal()
    a = db.query(Agent).filter(Agent.slug == slug).first()
    if a:
        db.delete(a)
        db.commit()
    db.close()
    return redirect(url_for("admin_home"))

# ------------------------------------------------------------------------------
# Public Card / QR / vCard
# ------------------------------------------------------------------------------

@app.route("/<slug>")
def public_card(slug):
    db = SessionLocal()
    a = db.query(Agent).filter(Agent.slug == slug).first()
    db.close()
    if not a:
        return render_template("404.html"), 404
    # Prepara campi comodi nei template
    emails = parse_list(a.emails)
    websites = parse_list(a.websites)
    addresses = [x for x in (a.addresses or "").splitlines() if x.strip()]

    # link WhatsApp: accetto numero o link wa.me
    wa_link = ""
    if a.whatsapp:
        wa = a.whatsapp.strip()
        if wa.startswith("http"):
            wa_link = wa
        else:
            wa_link = f"https://wa.me/{wa}"

    return render_template(
        "card.html",
        agent=a,
        emails=emails,
        websites=websites,
        addresses=addresses,
        whatsapp_link=wa_link,
    )

@app.route("/qr/<slug>.png")
def qr_png(slug):
    # genero QR verso la card pubblica
    url = f"{abs_base_url()}/{slug}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

@app.route("/qr/<slug>.svg")
def qr_svg(slug):
    url = f"{abs_base_url()}/{slug}"
    factory = SvgImage
    img = qrcode.make(url, image_factory=factory)
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype="image/svg+xml")

@app.route("/vcard/<slug>.vcf")
def vcard(slug):
    db = SessionLocal()
    a = db.query(Agent).filter(Agent.slug == slug).first()
    db.close()
    if not a:
        abort(404)

    emails = parse_list(a.emails)
    websites = parse_list(a.websites)
    adr = [x for x in (a.addresses or "").splitlines() if x.strip()]

    # vCard 3.0 semplice
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{a.name};;;;",
        f"FN:{a.name}",
    ]
    if a.company:
        lines.append(f"ORG:{a.company}")
    if a.role:
        lines.append(f"TITLE:{a.role}")
    if a.phone_mobile:
        lines.append(f"TEL;TYPE=CELL:{a.phone_mobile}")
    if a.phone_office:
        lines.append(f"TEL;TYPE=WORK:{a.phone_office}")
    for e in emails:
        lines.append(f"EMAIL;TYPE=INTERNET:{e}")
    for w in websites:
        lines.append(f"URL:{w}")
    for address in adr[:3]:
        lines.append(f"ADR;TYPE=WORK:;;{address};;;;")
    lines.append("END:VCARD")

    data = "\r\n".join(lines).encode("utf-8")
    return send_file(
        io.BytesIO(data),
        mimetype="text/vcard",
        as_attachment=True,
        download_name=f"{a.slug}.vcf",
    )

# ------------------------------------------------------------------------------
# Avvio / Inizializzazione Firebase
# ------------------------------------------------------------------------------

@app.before_request
def _maybe_init_firebase():
    """
    Inizializza Firebase Storage una sola volta nel primo request
    (evita problemi su ambienti serverless).
    """
    global gcs_bucket
    if not USE_FIREBASE or gcs_bucket is not None:
        return

    bucket_name = os.getenv("FIREBASE_BUCKET")
    creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")

    if not bucket_name or not creds_json:
        # configurazione non completa -> non usare firebase
        return

    try:
        info = json.loads(creds_json)
        creds = google.oauth2.service_account.Credentials.from_service_account_info(info)
        client = storage.Client(credentials=creds, project=info.get("project_id"))
        gcs_bucket = client.bucket(bucket_name)
    except Exception as e:
        # se qualcosa va storto, disattiva firebase
        gcs_bucket = None

# ------------------------------------------------------------------------------
# Gunicorn entrypoint
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # sviluppo locale
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
