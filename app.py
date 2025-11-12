# app.py  — v2 con upload locali e card robusta
from __future__ import annotations
import os, json, re
from pathlib import Path
from io import BytesIO
from datetime import datetime
from werkzeug.utils import secure_filename

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_file, send_from_directory, abort, request as flask_request
)

import qrcode


# ---------------------- Config ----------------------
app = Flask(__name__)

secret_path = Path("/etc/secrets/SECRET_KEY")
if secret_path.exists():
    app.secret_key = secret_path.read_text().strip()
else:
    app.secret_key = os.getenv("APP_SECRET", "dev-secret-change-me")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
if not ADMIN_PASSWORD:
    raise RuntimeError("Missing ENV ADMIN_PASSWORD")

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")

# storage “DB”
DATA_DIR = Path("data"); DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = DATA_DIR / "db.json"

# upload dir (servita via /media/…)
UPLOAD_DIR = DATA_DIR / "uploads"; UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMG = {"png","jpg","jpeg","webp","gif"}
ALLOWED_PDF = {"pdf"}

def _load_db():
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save_db(db: dict):
    tmp = DB_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DB_FILE)

DB = _load_db()

def is_admin(): return bool(session.get("admin"))
def normalize_slug(s:str)->str: return (s or "").strip().lower()

# filtro per link
@app.template_filter("ensure_http")
def ensure_http(u: str | None):
    if not u: return ""
    u = u.strip()
    if u.startswith(("http://","https://")): return u
    return "https://" + u

def _safe_ext(filename:str)->str:
    fn = secure_filename(filename)
    m = re.search(r"\.([A-Za-z0-9]+)$", fn)
    return (m.group(1).lower() if m else "")

def _save_upload(file_storage, subdir:str, allowed:set[str]) -> str | None:
    if not file_storage or not getattr(file_storage,"filename",None):
        return None
    ext = _safe_ext(file_storage.filename)
    if ext not in allowed:
        return None
    folder = UPLOAD_DIR / subdir
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    filename = secure_filename(f"{stamp}.{ext}")
    file_path = folder / filename
    file_storage.save(file_path)
    # URL pubblico locale
    return f"/media/{subdir}/{filename}"


# ---------------------- Health ----------------------
@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat()}


# ---------------------- Auth ------------------------
@app.get("/login")
def login():
    if is_admin(): return redirect(url_for("admin_home"))
    return render_template("login.html")

@app.post("/login")
def do_login():
    if request.form.get("password","") == ADMIN_PASSWORD:
        session["admin"] = True
        return redirect(url_for("admin_home"))
    return render_template("login.html", error="Password non corretta"), 401

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------- Admin -----------------------
@app.get("/")
def root_redirect():
    return redirect(url_for("admin_home"))

@app.get("/admin")
def admin_home():
    if not is_admin(): return redirect(url_for("login"))
    agents = sorted(DB.values(), key=lambda a: (a.get("name") or "").lower())
    return render_template("admin_list.html", agents=agents)

@app.get("/admin/new")
def admin_new():
    if not is_admin(): return redirect(url_for("login"))
    return render_template("agent_form.html", agent=None, error=None)

@app.post("/admin/new")
def admin_new_post():
    if not is_admin(): return redirect(url_for("login"))

    # campi testuali
    fields = [
        "slug","name","company","role","bio",
        "phone_mobile","phone_office","emails","websites",
        "facebook","instagram","linkedin","tiktok",
        "telegram","whatsapp","pec","piva","sdi","addresses",
        "photo_url","gallery_urls","pdf1_url","pdf2_url","pdf3_url","pdf4_url",
    ]
    agent = {f: request.form.get(f,"").strip() for f in fields}
    agent["slug"] = normalize_slug(agent["slug"])
    if not agent["slug"]:
        return render_template("agent_form.html", agent=agent, error="Slug obbligatorio"), 400
    if agent["slug"] in DB:
        return render_template("agent_form.html", agent=agent, error="Slug già esistente"), 400

    # upload singoli (foto & pdf)
    photo_file = request.files.get("photo_file")
    if photo_file:
        saved = _save_upload(photo_file, "photos", ALLOWED_IMG)
        if saved: agent["photo_url"] = saved

    for i in range(1,5):
        pf = request.files.get(f"pdf{i}_file")
        if pf:
            saved = _save_upload(pf, "pdf", ALLOWED_PDF)
            if saved: agent[f"pdf{i}_url"] = saved

    # upload multipli galleria
    gallery_files = request.files.getlist("gallery_files")
    gallery_saved = []
    for gf in gallery_files:
        s = _save_upload(gf, "gallery", ALLOWED_IMG)
        if s: gallery_saved.append(s)

    # merge con eventuali URL incollati
    urls_from_text = [u.strip() for u in (agent.get("gallery_urls") or "").split(",") if u.strip()]
    agent["gallery_urls"] = ",".join(urls_from_text + gallery_saved)

    DB[agent["slug"]] = agent
    _save_db(DB)
    return redirect(url_for("admin_home"))

@app.get("/admin/<slug>/edit")
def admin_edit(slug):
    if not is_admin(): return redirect(url_for("login"))
    slug = normalize_slug(slug)
    agent = DB.get(slug)
    if not agent: return render_template("404.html"), 404
    return render_template("agent_form.html", agent=agent, error=None)

@app.post("/admin/<slug>/edit")
def admin_edit_post(slug):
    if not is_admin(): return redirect(url_for("login"))
    old_slug = normalize_slug(slug)
    agent = DB.get(old_slug)
    if not agent: return render_template("404.html"), 404

    fields = [
        "slug","name","company","role","bio",
        "phone_mobile","phone_office","emails","websites",
        "facebook","instagram","linkedin","tiktok",
        "telegram","whatsapp","pec","piva","sdi","addresses",
        "photo_url","gallery_urls","pdf1_url","pdf2_url","pdf3_url","pdf4_url",
    ]
    new_data = {f: request.form.get(f,"").strip() for f in fields}
    new_slug = normalize_slug(new_data.get("slug"))
    if not new_slug:
        return render_template("agent_form.html", agent=new_data, error="Slug obbligatorio"), 400
    if new_slug != old_slug and new_slug in DB:
        return render_template("agent_form.html", agent=new_data, error="Slug già esistente"), 400

    # upload: se carichi un file, sovrascrive l’URL del campo
    photo_file = request.files.get("photo_file")
    if photo_file:
        s = _save_upload(photo_file, "photos", ALLOWED_IMG)
        if s: new_data["photo_url"] = s

    for i in range(1,5):
        pf = request.files.get(f"pdf{i}_file")
        if pf:
            s = _save_upload(pf, "pdf", ALLOWED_PDF)
            if s: new_data[f"pdf{i}_url"] = s

    gallery_files = request.files.getlist("gallery_files")
    gallery_saved = []
    for gf in gallery_files:
        s = _save_upload(gf, "gallery", ALLOWED_IMG)
        if s: gallery_saved.append(s)
    urls_from_text = [u.strip() for u in (new_data.get("gallery_urls") or "").split(",") if u.strip()]
    new_data["gallery_urls"] = ",".join(urls_from_text + gallery_saved)

    if new_slug != old_slug:
        DB.pop(old_slug, None)
    DB[new_slug] = new_data
    _save_db(DB)
    return redirect(url_for("admin_home"))

@app.post("/admin/<slug>/delete")
def admin_delete(slug):
    if not is_admin(): return redirect(url_for("login"))
    DB.pop(normalize_slug(slug), None)
    _save_db(DB)
    return redirect(url_for("admin_home"))


# ---------------------- Media statici ----------------
@app.get("/media/<path:fp>")
def media(fp):
    # serve i file caricati
    return send_from_directory(UPLOAD_DIR, fp, as_attachment=False)


# ---------------------- Pubblico ---------------------
@app.get("/<slug>")
def public_card(slug):
    slug = normalize_slug(slug)
    agent = DB.get(slug)
    if not agent: return render_template("404.html"), 404
    return render_template("card.html", agent=agent)

@app.get("/vcard/<slug>.vcf")
def vcard(slug):
    slug = normalize_slug(slug)
    a = DB.get(slug)
    if not a: return render_template("404.html"), 404

    name = a.get("name","")
    mobile = (a.get("phone_mobile") or "").replace(" ", "")
    office = (a.get("phone_office") or "").replace(" ", "")
    emails = [e.strip() for e in (a.get("emails") or "").split(",") if e.strip()]

    lines = ["BEGIN:VCARD","VERSION:3.0",f"N:{name};;;;",f"FN:{name}"]
    if mobile: lines.append(f"TEL;TYPE=CELL:{mobile}")
    if office: lines.append(f"TEL;TYPE=WORK:{office}")
    for e in emails: lines.append(f"EMAIL;TYPE=INTERNET:{e}")
    lines.append("END:VCARD")
    buf = BytesIO("\r\n".join(lines).encode("utf-8"))
    return send_file(buf, mimetype="text/vcard", download_name=f"{slug}.vcf")

@app.get("/qr/<slug>.png")
def qr_png(slug):
    slug = normalize_slug(slug)
    if slug not in DB: return render_template("404.html"), 404
    base = BASE_URL or flask_request.host_url.rstrip("/")
    url = f"{base}/{slug}"
    img = qrcode.make(url)
    b = BytesIO(); img.save(b, format="PNG"); b.seek(0)
    return send_file(b, mimetype="image/png")


# ---------------------- Errori -----------------------
@app.errorhandler(404)
def err404(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def err500(e):
    return render_template("500.html") if Path("templates/500.html").exists() else ("Internal Server Error", 500)


# ---------------------- Run locale -------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

