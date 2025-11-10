import os
from flask import Flask, render_template, request, redirect, url_for, send_file, session, abort, Response
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
from io import BytesIO
from datetime import datetime, timedelta
import qrcode, uuid, tempfile

load_dotenv()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
APP_SECRET = os.getenv("APP_SECRET", "dev_secret")
BASE_URL = (os.getenv("BASE_URL", "").strip().rstrip("/"))
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
FIREBASE_BUCKET = os.getenv("FIREBASE_BUCKET")
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON")

app = Flask(__name__)
app.secret_key = APP_SECRET
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

DB_URL = "sqlite:///data.db"
engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Agent(Base):
    __tablename__ = "agents"
    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    company = Column(String, nullable=True)
    role = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    phone_mobile = Column(String, nullable=True)
    phone_office = Column(String, nullable=True)
    emails = Column(String, nullable=True)
    websites = Column(String, nullable=True)
    facebook = Column(String, nullable=True)
    instagram = Column(String, nullable=True)
    linkedin = Column(String, nullable=True)
    tiktok = Column(String, nullable=True)
    telegram = Column(String, nullable=True)
    whatsapp = Column(String, nullable=True)
    pec = Column(String, nullable=True)
    piva = Column(String, nullable=True)
    sdi = Column(String, nullable=True)
    addresses = Column(Text, nullable=True)
    photo_url = Column(String, nullable=True)
    gallery_urls = Column(Text, nullable=True)
    pdf1_url = Column(String, nullable=True)
    pdf2_url = Column(String, nullable=True)

Base.metadata.create_all(engine)

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
      if not session.get("admin"):
          return redirect(url_for("login", next=request.path))
      return f(*args, **kwargs)
    return wrapper

def get_storage_client():
    try:
        if not (FIREBASE_BUCKET and FIREBASE_CREDENTIALS_JSON):
            return None
        from google.cloud import storage
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        tmp.write(FIREBASE_CREDENTIALS_JSON.encode("utf-8"))
        tmp.flush()
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name
        return storage.Client(project=FIREBASE_PROJECT_ID)
    except Exception:
        return None

def upload_to_firebase(file_storage, folder="uploads"):
    try:
        client = get_storage_client()
        if not client:
            return None
        bucket = client.bucket(FIREBASE_BUCKET)
        import os
        ext = os.path.splitext(file_storage.filename or "")[1].lower()
        key = f"{folder}/{datetime.utcnow().strftime('%Y/%m/%d')}/{uuid.uuid4().hex}{ext}"
        blob = bucket.blob(key)
        blob.upload_from_file(file_storage.stream, content_type=file_storage.mimetype)
        url = blob.generate_signed_url(expiration=datetime.utcnow() + timedelta(days=3650), method="GET")
        return url
    except Exception:
        return None

def get_base_url():
    if BASE_URL:
        return BASE_URL
    from flask import request
    return request.url_root.strip().rstrip("/")

@app.get("/health")
def health():
    return "ok", 200

@app.get("/")
def root():
    return redirect(url_for("admin_home")) if session.get("admin") else redirect(url_for("login"))

@app.get("/login")
def login():
    return render_template("login.html", error=None, next=request.args.get("next", "/admin"))

@app.post("/login")
def login_post():
    pw = request.form.get("password", "")
    nxt = request.form.get("next", "/admin")
    if pw == ADMIN_PASSWORD:
        session["admin"] = True
        return redirect(nxt)
    return render_template("login.html", error="Password errata", next=nxt)

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.get("/admin")
@admin_required
def admin_home():
    db = SessionLocal()
    agents = db.query(Agent).order_by(Agent.name).all()
    return render_template("admin_list.html", agents=agents)

@app.get("/admin/new")
@admin_required
def admin_new():
    return render_template("agent_form.html", agent=None)

@app.post("/admin/new")
@admin_required
def admin_create():
    db = SessionLocal()
    fields = ["slug","name","company","role","bio","phone_mobile","phone_office","emails","websites",
              "facebook","instagram","linkedin","tiktok","telegram","whatsapp","pec","piva","sdi","addresses"]
    data = {k: request.form.get(k,"").strip() for k in fields}
    if not data["slug"] or not data["name"]:
        return "Slug e Nome sono obbligatori", 400
    if db.query(Agent).filter_by(slug=data["slug"]).first():
        return "Slug già esistente", 400

    photo = request.files.get("photo")
    pdf1  = request.files.get("pdf1")
    pdf2  = request.files.get("pdf2")
    gallery_files = request.files.getlist("gallery")

    photo_url = upload_to_firebase(photo,"photos") if photo and photo.filename else None
    pdf1_url = upload_to_firebase(pdf1,"pdf") if pdf1 and pdf1.filename else None
    pdf2_url = upload_to_firebase(pdf2,"pdf") if pdf2 and pdf2.filename else None
    gallery_urls = []
    for f in gallery_files[:12]:
        if f and f.filename:
            u = upload_to_firebase(f,"gallery")
            if u: gallery_urls.append(u)

    ag = Agent(**data, photo_url=photo_url, pdf1_url=pdf1_url, pdf2_url=pdf2_url,
               gallery_urls="|".join(gallery_urls) if gallery_urls else None)
    db.add(ag); db.commit()
    return redirect(url_for("admin_home"))

@app.get("/admin/<slug>/edit")
@admin_required
def admin_edit(slug):
    db = SessionLocal()
    ag = db.query(Agent).filter_by(slug=slug).first()
    if not ag: abort(404)
    return render_template("agent_form.html", agent=ag)

@app.post("/admin/<slug>/edit")
@admin_required
def admin_update(slug):
    db = SessionLocal()
    ag = db.query(Agent).filter_by(slug=slug).first()
    if not ag: abort(404)
    for k in ["slug","name","company","role","bio","phone_mobile","phone_office","emails","websites",
              "facebook","instagram","linkedin","tiktok","telegram","whatsapp","pec","piva","sdi","addresses"]:
        setattr(ag, k, request.form.get(k,"").strip())
    photo = request.files.get("photo")
    pdf1  = request.files.get("pdf1")
    pdf2  = request.files.get("pdf2")
    gallery_files = request.files.getlist("gallery")

    if photo and photo.filename:
        u = upload_to_firebase(photo,"photos")
        if u: ag.photo_url = u
    if pdf1 and pdf1.filename:
        u = upload_to_firebase(pdf1,"pdf")
        if u: ag.pdf1_url = u
    if pdf2 and pdf2.filename:
        u = upload_to_firebase(pdf2,"pdf")
        if u: ag.pdf2_url = u
    if gallery_files and any(g.filename for g in gallery_files):
        urls = []
        for f in gallery_files[:12]:
            if f and f.filename:
                u = upload_to_firebase(f,"gallery")
                if u: urls.append(u)
        if urls: ag.gallery_urls = "|".join(urls)
    db.commit()
    return redirect(url_for("admin_home"))

@app.post("/admin/<slug>/delete")
@admin_required
def admin_delete(slug):
    db = SessionLocal()
    ag = db.query(Agent).filter_by(slug=slug).first()
    if ag: db.delete(ag); db.commit()
    return redirect(url_for("admin_home"))

@app.get("/<slug>")
def public_card(slug):
    db = SessionLocal()
    ag = db.query(Agent).filter_by(slug=slug).first()
    if not ag: abort(404)
    gallery = ag.gallery_urls.split("|") if ag.gallery_urls else []
    emails = [e.strip() for e in (ag.emails or "").split(",") if e.strip()]
    websites = [w.strip() for w in (ag.websites or "").split(",") if w.strip()]
    addresses = [a.strip() for a in (ag.addresses or "").split("\n") if a.strip()]
    base = get_base_url()
    return render_template("card.html", ag=ag, base_url=base,
                           gallery=gallery, emails=emails, websites=websites, addresses=addresses)

@app.get("/<slug>.vcf")
def vcard(slug):
    db = SessionLocal()
    ag = db.query(Agent).filter_by(slug=slug).first()
    if not ag: abort(404)
    lines = ["BEGIN:VCARD","VERSION:3.0",f"FN:{ag.name}",f"N:{ag.name};;;;"]
    if getattr(ag, "role", None): lines.append(f"TITLE:{ag.role}")
    if getattr(ag, "phone_mobile", None): lines.append(f"TEL;TYPE=CELL:{ag.phone_mobile}")
    if getattr(ag, "phone_office", None): lines.append(f"TEL;TYPE=WORK:{ag.phone_office}")
    if getattr(ag, "emails", None):
        for e in [x.strip() for x in ag.emails.split(",") if x.strip()]:
            lines.append(f"EMAIL;TYPE=WORK:{e}")
    if getattr(ag, "websites", None):
        for w in [x.strip() for x in ag.websites.split(",") if x.strip()]:
            lines.append(f"URL:{w}")
    if getattr(ag, "company", None): lines.append(f"ORG:{ag.company}")
    if getattr(ag, "piva", None): lines.append(f"X-TAX-ID:{ag.piva}")
    if getattr(ag, "sdi", None): lines.append(f"X-SDI-CODE:{ag.sdi}")
    note = []
    if getattr(ag, "piva", None): note.append(f"Partita IVA: {ag.piva}")
    if getattr(ag, "sdi", None): note.append(f"SDI: {ag.sdi}")
    if note: lines.append("NOTE:" + " | ".join(note))
    lines.append("END:VCARD")
    content = "\r\n".join(lines)
    if request.args.get("download") == "1":
        resp = Response(content, mimetype="text/vcard; charset=utf-8")
        resp.headers["Content-Disposition"] = f'attachment; filename=\"{ag.slug}.vcf\"'
        return resp
    return Response(content, mimetype="text/vcard; charset=utf-8")

@app.get("/qr/<slug>.png")
def qr_png(slug):
    db = SessionLocal()
    ag = db.query(Agent).filter_by(slug=slug).first()
    if not ag: abort(404)
    profile_url = f"{get_base_url()}/{ag.slug}"
    qr = qrcode.QRCode(border=2, box_size=10)
    qr.add_data(profile_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0a2a66", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", download_name=f"qr_{ag.slug}.png")

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
