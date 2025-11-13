import os
import io
import json
import qrcode
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, send_file, abort
)
from werkzeug.utils import secure_filename

# Firebase
import firebase_admin
from firebase_admin import credentials, storage, firestore

# ----------------------------------------------------------
#   CONFIGURAZIONE APP
# ----------------------------------------------------------
app = Flask(__name__)

# Secret key
app.secret_key = os.getenv("APP_SECRET", "supersecret")

# Admin
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

# Base URL — per generare QR e link pubblici
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

# ----------------------------------------------------------
#   FIREBASE
# ----------------------------------------------------------
firebase_project = os.getenv("FIREBASE_PROJECT_ID", "")
firebase_bucket = os.getenv("FIREBASE_BUCKET", "")
firebase_json = os.getenv("FIREBASE_CREDENTIALS_JSON", "")

if firebase_project and firebase_bucket and firebase_json:
    cred = credentials.Certificate(json.loads(firebase_json))
    firebase_admin.initialize_app(cred, {
        'storageBucket': firebase_bucket
    })
    bucket = storage.bucket()
    db = firestore.client()
else:
    firebase_project = None
    bucket = None
    db = None


# ----------------------------------------------------------
#   FUNZIONE - SALVA FILE SU FIREBASE
# ----------------------------------------------------------
def upload_file_to_firebase(file, folder):
    if not bucket:
        return None

    filename = secure_filename(file.filename)
    path = f"{folder}/{datetime.utcnow().timestamp()}_{filename}"

    blob = bucket.blob(path)
    blob.upload_from_file(file, content_type=file.content_type)
    blob.make_public()
    return blob.public_url


# ----------------------------------------------------------
#   HOME (Reindirizza login)
# ----------------------------------------------------------
@app.route("/")
def home():
    return redirect(url_for("login"))


# ----------------------------------------------------------
#   LOGIN ADMIN
# ----------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_list"))
        return render_template("login.html", error=True)

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ----------------------------------------------------------
#   DASHBOARD ADMIN
# ----------------------------------------------------------
@app.route("/admin")
def admin_list():
    if not session.get("admin"):
        return redirect(url_for("login"))

    agents = []
    docs = db.collection("agents").stream()
    for d in docs:
        x = d.to_dict()
        x["id"] = d.id
        agents.append(x)

    return render_template("admin_list.html", agents=agents)


# ----------------------------------------------------------
#   CREA / MODIFICA AGENTE
# ----------------------------------------------------------
@app.route("/admin/new", methods=["GET", "POST"])
@app.route("/admin/edit/<slug>", methods=["GET", "POST"])
def admin_edit(slug=None):
    if not session.get("admin"):
        return redirect(url_for("login"))

    agent_ref = db.collection("agents").document(slug) if slug else None
    agent_data = agent_ref.get().to_dict() if agent_ref and agent_ref.get().exists else {}

    if request.method == "POST":
        new_slug = request.form.get("slug").strip().lower()
        if not new_slug:
            return render_template("agent_form.html", agent=agent_data, error="Slug obbligatorio")

        data = {
            "slug": new_slug,
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
            "addresses": request.form.get("addresses"),
            "updated": datetime.utcnow()
        }

        # FOTO PROFILO
        if "photo" in request.files and request.files["photo"].filename:
            data["photo_url"] = upload_file_to_firebase(request.files["photo"], "photos")

        # PDF
        for idx in ["pdf1", "pdf2", "pdf3", "pdf4"]:
            if idx in request.files and request.files[idx].filename:
                data[idx] = upload_file_to_firebase(request.files[idx], "pdf")

        # GALLERIA
        gallery_urls = []
        if "gallery" in request.files:
            for f in request.files.getlist("gallery"):
                if f.filename:
                    gallery_urls.append(upload_file_to_firebase(f, "gallery"))
        if gallery_urls:
            data["gallery"] = gallery_urls

        # Salva su Firebase
        db.collection("agents").document(new_slug).set(data, merge=True)

        return redirect(url_for("admin_list"))

    return render_template("agent_form.html", agent=agent_data)


# ----------------------------------------------------------
#   ELIMINA AGENTE
# ----------------------------------------------------------
@app.route("/admin/delete/<slug>", methods=["POST"])
def admin_delete(slug):
    if not session.get("admin"):
        return redirect(url_for("login"))

    db.collection("agents").document(slug).delete()
    return redirect(url_for("admin_list"))


# ----------------------------------------------------------
#   CARD PUBBLICA
# ----------------------------------------------------------
@app.route("/<slug>")
def public_card(slug):
    doc = db.collection("agents").document(slug).get()
    if not doc.exists:
        return render_template("404.html")

    data = doc.to_dict()

    # Registra visita
    db.collection("visits").add({
        "slug": slug,
        "timestamp": datetime.utcnow(),
        "ip": request.remote_addr
    })

    return render_template("card.html", agent=data)


# ----------------------------------------------------------
#   STATISTICHE VISITE
# ----------------------------------------------------------
@app.route("/stats/<slug>")
def stats(slug):
    visits = db.collection("visits").where("slug", "==", slug).stream()
    timestamps = [v.to_dict()["timestamp"] for v in visits]
    return {"slug": slug, "visite_totali": len(timestamps)}


# ----------------------------------------------------------
#   GENERA QR CODE
# ----------------------------------------------------------
@app.route("/qr/<slug>.png")
def qr_png(slug):
    url = f"{BASE_URL}/{slug}"
    img = qrcode.make(url)
    buffer = io.BytesIO()
    img.save(buffer, "PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")


# ----------------------------------------------------------
#   GENERA vCARD
# ----------------------------------------------------------
@app.route("/vcard/<slug>")
def vcard(slug):
    doc = db.collection("agents").document(slug).get()
    if not doc.exists:
        abort(404)

    a = doc.to_dict()

    vcf = f"""BEGIN:VCARD
VERSION:3.0
N:{a.get('name')}
ORG:{a.get('company')}
TITLE:{a.get('role')}
TEL;CELL:{a.get('phone_mobile')}
TEL;WORK:{a.get('phone_office')}
EMAIL:{a.get('emails')}
URL:{a.get('websites')}
END:VCARD"""

    return Response(
        vcf,
        mimetype="text/vcard",
        headers={"Content-Disposition": f"attachment; filename={slug}.vcf"}
    )


# ----------------------------------------------------------
#   404
# ----------------------------------------------------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


# ----------------------------------------------------------
#   AVVIO
# ----------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
