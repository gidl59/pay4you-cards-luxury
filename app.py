import os
from flask import Flask, render_template, request, redirect, url_for, session, send_file, abort
from werkzeug.utils import secure_filename
from firebase_admin import credentials, initialize_app, storage
import uuid

# --------------------------------
# CONFIG APP
# --------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET", "testsecret123")

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "test")

BASE_URL = os.getenv("BASE_URL", "https://pay4you-cards-luxury.onrender.com")

# --------------------------------
# FIREBASE
# --------------------------------
cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
bucket_name = os.getenv("FIREBASE_BUCKET")

if cred_json and bucket_name:
    import json
    cred_dict = json.loads(cred_json)
    cred = credentials.Certificate(cred_dict)
    firebase_app = initialize_app(cred, {
        "storageBucket": bucket_name
    })
    bucket = storage.bucket()
else:
    firebase_app = None
    bucket = None

# --------------------------------
# CARICAMENTO SU FIREBASE
# --------------------------------
def upload_file_to_firebase(file):
    if not file or not bucket:
        return None

    filename = secure_filename(file.filename)
    ext = filename.split(".")[-1]
    blob_name = f"uploads/{uuid.uuid4()}.{ext}"

    blob = bucket.blob(blob_name)
    blob.upload_from_file(file, content_type=file.content_type)

    blob.make_public()
    return blob.public_url


# --------------------------------
# DATABASE "FAKE" su memoria
# (Render NON permette scrittura file)
# --------------------------------
AGENTS = {}


# --------------------------------
# LOGIN
# --------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_home"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------
# DASHBOARD ADMIN
# --------------------------------
@app.route("/admin")
def admin_home():
    if not session.get("admin"):
        return redirect(url_for("login"))
    return render_template("admin_list.html", agents=AGENTS.values())


# --------------------------------
# NUOVO AGENTE
# --------------------------------
@app.route("/admin/new", methods=["GET", "POST"])
def admin_new():
    if not session.get("admin"):
        return redirect(url_for("login"))

    if request.method == "POST":
        slug = request.form.get("slug").strip().lower()
        if slug in AGENTS:
            return "Slug già esistente."

        # Foto profilo
        photo_url = upload_file_to_firebase(request.files.get("photo"))

        # Gallery
        gallery_urls = []
        for f in request.files.getlist("gallery"):
            url = upload_file_to_firebase(f)
            if url:
                gallery_urls.append(url)

        # PDF
        pdf1_url = upload_file_to_firebase(request.files.get("pdf1"))
        pdf2_url = upload_file_to_firebase(request.files.get("pdf2"))

        AGENTS[slug] = {
            "slug": slug,
            "name": request.form.get("name"),
            "company": request.form.get("company"),
            "role": request.form.get("role"),
            "bio": request.form.get("bio"),
            "phone_mobile": request.form.get("phone_mobile"),
            "phone_office": request.form.get("phone_office"),
            "emails": request.form.get("emails"),
            "websites": request.form.get("websites"),

            "facebook": request.form.get("facebook"),
            "instagram": request.form.get("instagram"),
            "linkedin": request.form.get("linkedin"),
            "tiktok": request.form.get("tiktok"),
            "telegram": request.form.get("telegram"),
            "whatsapp": request.form.get("whatsapp"),

            "pec": request.form.get("pec"),
            "piva": request.form.get("piva"),
            "sdi": request.form.get("sdi"),
            "addresses": request.form.get("addresses"),

            "photo": photo_url,
            "gallery": gallery_urls,
            "pdf1": pdf1_url,
            "pdf2": pdf2_url,
        }

        return redirect(url_for("admin_home"))

    return render_template("agent_form.html", agent=None)


# --------------------------------
# PAGINA PUBBLICA AGENTE
# --------------------------------
@app.route("/<slug>")
def public_card(slug):
    agent = AGENTS.get(slug)
    if not agent:
        return render_template("404.html"), 404
    return render_template("card.html", a=agent)


# --------------------------------
# QR CODE PNG
# --------------------------------
import qrcode
from io import BytesIO

@app.route("/qr/<slug>")
def qr_png(slug):
    if slug not in AGENTS:
        abort(404)

    img = qrcode.make(f"{BASE_URL}/{slug}")
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# --------------------------------
# HEALTH CHECK
# --------------------------------
@app.route("/health")
def health():
    return "OK"


# --------------------------------
# AVVIO
# --------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
