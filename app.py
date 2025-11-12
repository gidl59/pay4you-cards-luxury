import os, io, json, datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_file, abort
from werkzeug.utils import secure_filename
import qrcode

# ========= Config =========
APP_SECRET = os.getenv("APP_SECRET") or "dev-secret"
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "test")
BASE_URL = os.getenv("BASE_URL", "http://localhost:10000").rstrip("/")

# Opzionale Firebase (se non configurato, salva localmente in /static/uploads)
FIREBASE_BUCKET = os.getenv("FIREBASE_BUCKET", "").strip()
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "").strip()
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON", "").strip()

app = Flask(__name__)
app.secret_key = APP_SECRET
os.makedirs("static/uploads", exist_ok=True)
DATA_PATH = "data"
os.makedirs(DATA_PATH, exist_ok=True)
AGENTS_JSON = os.path.join(DATA_PATH, "agents.json")

# ========= Helpers =========
def load_agents():
    if not os.path.exists(AGENTS_JSON):
        return []
    with open(AGENTS_JSON, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return []

def save_agents(items):
    with open(AGENTS_JSON, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

def get_agent(slug):
    for a in load_agents():
        if a.get("slug") == slug:
            return a
    return None

def put_agent(agent):
    items = load_agents()
    # replace or insert
    found = False
    for i, a in enumerate(items):
        if a.get("slug") == agent.get("slug"):
            items[i] = agent
            found = True
            break
    if not found:
        items.append(agent)
    save_agents(items)

def remove_agent(slug):
    items = [a for a in load_agents() if a.get("slug") != slug]
    save_agents(items)

@app.template_filter("ensure_http")
def ensure_http(url):
    if not url: return ""
    u = url.strip()
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return "https://" + u

def _filename_with_ts(filename):
    base = secure_filename(filename)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    if "." in base:
        name, ext = base.rsplit(".", 1)
        return f"{name}-{ts}.{ext}"
    return f"{base}-{ts}"

# --- Storage: Firebase (se settato) oppure locale ---
_storage_client = None
def upload_file(file_storage, folder="misc"):
    global _storage_client
    fname = _filename_with_ts(file_storage.filename)
    if FIREBASE_BUCKET and FIREBASE_PROJECT_ID and FIREBASE_CREDENTIALS_JSON:
        # Firebase/Google Cloud Storage
        try:
            from google.cloud import storage
            import json as _json
            if _storage_client is None:
                creds = _json.loads(FIREBASE_CREDENTIALS_JSON)
                _storage_client = storage.Client.from_service_account_info(creds, project=FIREBASE_PROJECT_ID)
            bucket = _storage_client.bucket(FIREBASE_BUCKET)
            blob = bucket.blob(f"{folder}/{fname}")
            blob.upload_from_file(file_storage.stream, content_type=file_storage.mimetype)
            blob.make_public()
            return blob.public_url
        except Exception as e:
            print("Firebase upload error:", e)
            # fallback locale
    # Local
    path = os.path.join("static/uploads", folder)
    os.makedirs(path, exist_ok=True)
    full = os.path.join(path, fname)
    file_storage.save(full)
    return url_for("static", filename=f"uploads/{folder}/{fname}", _external=True)

# ========= Routes =========
@app.route("/health")
def health():
    return {"ok": True}

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        pwd = (request.form.get("password") or "").strip()
        if pwd == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_home"))
        return render_template("login.html", error="Password errata")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ----- ADMIN -----
def require_admin():
    if not session.get("admin"):
        abort(403)

@app.route("/admin")
def admin_home():
    require_admin()
    return render_template("admin_list.html", agents=load_agents())

@app.route("/admin/new", methods=["GET","POST"])
def admin_new():
    require_admin()
    if request.method == "POST":
        return _save_agent(is_new=True)
    return render_template("agent_form.html", agent=None)

@app.route("/admin/<slug>/edit", methods=["GET","POST"])
def admin_edit(slug):
    require_admin()
    agent = get_agent(slug)
    if not agent: abort(404)
    if request.method == "POST":
        return _save_agent(is_new=False, current=agent)
    return render_template("agent_form.html", agent=agent)

@app.route("/admin/<slug>/delete", methods=["POST"])
def admin_delete(slug):
    require_admin()
    remove_agent(slug)
    return redirect(url_for("admin_home"))

def _save_agent(is_new, current=None):
    # campi testuali
    fields = [
        "slug","name","company","role","bio",
        "phone_mobile","phone_office","phones_extra",
        "emails","websites",
        "facebook","instagram","linkedin","tiktok","telegram","whatsapp",
        "photo_y","photo_zoom"
    ]
    data = current.copy() if (current and not is_new) else {}
    for f in fields:
        data[f] = (request.form.get(f) or "").strip()

    # normalizza slug
    data["slug"] = data["slug"].strip().lower()

    # foto profilo (file) oppure URL incollato
    photo_file = request.files.get("photo")
    if photo_file and photo_file.filename:
        data["photo_url"] = upload_file(photo_file, "photo")
    else:
        # se l'utente ha inserito un URL manuale
        manual_photo = (request.form.get("photo_url") or "").strip()
        if manual_photo:
            data["photo_url"] = manual_photo

    # PDF (fino a 4) - file o URL
    pdf_urls = []
    for i in range(1,5):
        f = request.files.get(f"pdf{i}")
        if f and f.filename:
            pdf_urls.append(upload_file(f, "pdf"))
        else:
            u = (request.form.get(f"pdf{i}_url") or "").strip()
            if u: pdf_urls.append(u)
    data["pdf_urls"] = ",".join(pdf_urls)

    # Galleria multipla - file o URL (separa con virgola)
    gallery_urls = []
    for g in request.files.getlist("gallery"):
        if g and g.filename:
            gallery_urls.append(upload_file(g, "gallery"))
    extra_gal = (request.form.get("gallery_urls") or "").strip()
    if extra_gal:
        gallery_urls.extend([x.strip() for x in extra_gal.split(",") if x.strip()])
    data["gallery_urls"] = ",".join(gallery_urls)

    put_agent(data)
    return redirect(url_for("admin_home"))

# ----- PUBLIC CARD -----
@app.route("/")
def root():
    # redirect semplice alla login oppure ad admin se già autenticato
    if session.get("admin"):
        return redirect(url_for("admin_home"))
    return redirect(url_for("login"))

@app.route("/<slug>")
def public_card(slug):
    a = get_agent(slug)
    if not a:
        return render_template("404.html"), 404
    return render_template("card.html", agent=a, BASE_URL=BASE_URL)

# vCard
@app.route("/vcard/<slug>")
def vcard(slug):
    a = get_agent(slug)
    if not a: abort(404)
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{a.get('name','')}",
        f"ORG:{a.get('company','')}",
        f"TITLE:{a.get('role','')}",
    ]
    # telefoni
    for num in [a.get("phone_mobile",""), a.get("phone_office","")]:
        if num.strip():
            lines.append(f"TEL;TYPE=CELL:{num.strip()}")
    for num in (a.get("phones_extra","") or "").split(","):
        if num.strip():
            lines.append(f"TEL;TYPE=VOICE:{num.strip()}")
    # email
    for e in (a.get("emails","") or "").split(","):
        if e.strip():
            lines.append(f"EMAIL;TYPE=INTERNET:{e.strip()}")
    # sito (primo della lista)
    site = (a.get("websites","") or "").split(",")[0].strip()
    if site:
        lines.append(f"URL:{ensure_http(site)}")
    lines.append("END:VCARD")
    v = "\r\n".join(lines)
    return send_file(io.BytesIO(v.encode("utf-8")), mimetype="text/vcard", as_attachment=True, download_name=f"{slug}.vcf")

# QR PNG
@app.route("/qr/<slug>.png")
def qr_png(slug):
    url = f"{BASE_URL}/{slug}"
    img = qrcode.make(url)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return send_file(bio, mimetype="image/png")

# 404 handler
@app.errorhandler(403)
def _403(_):
    return render_template("404.html", msg="Non autorizzato"), 403

@app.errorhandler(404)
def _404(_):
    return render_template("404.html"), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))

