import os
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, abort
from werkzeug.utils import secure_filename
import qrcode
from io import BytesIO

# ---------------------------
# CONFIGURAZIONE BASE
# ---------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET", "dev-secret")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "test")

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_IMG = {"png", "jpg", "jpeg"}
ALLOWED_PDF = {"pdf"}


# ---------------------------
# FUNZIONI DI SUPPORTO
# ---------------------------
def allowed(filename, types):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in types


def save_file(file, folder, types):
    """Salva file upload e ritorna relativo path /static/..."""
    if not file or file.filename == "":
        return None
    if not allowed(file.filename, types):
        return None

    os.makedirs(folder, exist_ok=True)

    filename = secure_filename(file.filename)
    full_path = os.path.join(folder, filename)
    file.save(full_path)

    return full_path.replace("static/", "")


# ---------------------------
# ROUTE DI BASE
# ---------------------------
@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pwd = request.form.get("password")
        if pwd == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_home"))
        return render_template("login.html", error="Password errata")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------
# DATABASE SEMPLICE (FILE JSON)
# ---------------------------
import json
DB_FILE = "agents.json"

def load_agents():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_agents(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# ---------------------------
# ADMIN DASHBOARD
# ---------------------------
@app.route("/admin")
def admin_home():
    if not session.get("admin"):
        return redirect(url_for("login"))
    agents = load_agents()
    return render_template("admin_list.html", agents=agents.values())


@app.route("/admin/new", methods=["GET", "POST"])
def admin_new():
    if not session.get("admin"):
        return redirect(url_for("login"))

    if request.method == "POST":
        slug = request.form.get("slug").strip().lower()
        if not slug:
            return render_template("agent_form.html", error="Slug obbligatorio")

        data = load_agents()
        if slug in data:
            return render_template("agent_form.html", error="Slug già esistente")

        # CREA CARTELLA PERSONALE
        agent_folder = os.path.join(UPLOAD_FOLDER, slug)
        os.makedirs(agent_folder, exist_ok=True)

        # FOTO PROFILO
        photo = save_file(
            request.files.get("photo"),
            agent_folder,
            ALLOWED_IMG
        )

        # GALLERIA
        gallery_files = request.files.getlist("gallery")
        gallery_paths = []
        for g in gallery_files:
            saved = save_file(g, agent_folder, ALLOWED_IMG)
            if saved:
                gallery_paths.append(saved)

        # PDF
        pdf1 = save_file(request.files.get("pdf1"), agent_folder, ALLOWED_PDF)
        pdf2 = save_file(request.files.get("pdf2"), agent_folder, ALLOWED_PDF)

        data[slug] = {
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
            "tiktok": request.form.get("tiktok"),
            "telegram": request.form.get("telegram"),
            "whatsapp": request.form.get("whatsapp"),
            "pec": request.form.get("pec"),
            "piva": request.form.get("piva"),
            "sdi": request.form.get("sdi"),
            "addresses": request.form.get("addresses"),
            "photo": photo,
            "gallery": gallery_paths,
            "pdf1": pdf1,
            "pdf2": pdf2
        }

        save_agents(data)
        return redirect(url_for("admin_home"))

    return render_template("agent_form.html")


@app.route("/admin/edit/<slug>", methods=["GET", "POST"])
def admin_edit(slug):
    if not session.get("admin"):
        return redirect(url_for("login"))

    data = load_agents()
    agent = data.get(slug)
    if not agent:
        abort(404)

    if request.method == "POST":
        agent["name"] = request.form.get("name")
        agent["company"] = request.form.get("company")
        agent["role"] = request.form.get("role")
        agent["bio"] = request.form.get("bio")
        agent["phone_mobile"] = request.form.get("phone_mobile")
        agent["phone_office"] = request.form.get("phone_office")
        agent["emails"] = request.form.get("emails")
        agent["websites"] = request.form.get("websites")
        agent["facebook"] = request.form.get("facebook")
        agent["instagram"] = request.form.get("instagram")
        agent["tiktok"] = request.form.get("tiktok")
        agent["telegram"] = request.form.get("telegram")
        agent["whatsapp"] = request.form.get("whatsapp")
        agent["pec"] = request.form.get("pec")
        agent["piva"] = request.form.get("piva")
        agent["sdi"] = request.form.get("sdi")
        agent["addresses"] = request.form.get("addresses")

        # AGGIORNAMENTI FILE
        agent_folder = os.path.join(UPLOAD_FOLDER, slug)

        new_photo = save_file(request.files.get("photo"), agent_folder, ALLOWED_IMG)
        if new_photo:
            agent["photo"] = new_photo

        new_gallery = request.files.getlist("gallery")
        for g in new_gallery:
            saved = save_file(g, agent_folder, ALLOWED_IMG)
            if saved:
                agent["gallery"].append(saved)

        new_pdf1 = save_file(request.files.get("pdf1"), agent_folder, ALLOWED_PDF)
        if new_pdf1:
            agent["pdf1"] = new_pdf1

        new_pdf2 = save_file(request.files.get("pdf2"), agent_folder, ALLOWED_PDF)
        if new_pdf2:
            agent["pdf2"] = new_pdf2

        save_agents(data)
        return redirect(url_for("admin_home"))

    return render_template("agent_form.html", agent=agent)


@app.route("/admin/delete/<slug>", methods=["POST"])
def admin_delete(slug):
    if not session.get("admin"):
        return redirect(url_for("login"))

    data = load_agents()
    if slug in data:
        del data[slug]
        save_agents(data)
    return redirect(url_for("admin_home"))


# ---------------------------
# CARD PUBBLICA
# ---------------------------
@app.route("/card/<slug>")
def public_card(slug):
    data = load_agents()
    agent = data.get(slug)
    if not agent:
        return render_template("404.html"), 404
    return render_template("card.html", agent=agent, base_url=BASE_URL)


# ---------------------------
# vCARD DOWNLOAD
# ---------------------------
@app.route("/vcard/<slug>")
def vcard(slug):
    data = load_agents()
    a = data.get(slug)
    if not a:
        abort(404)

    vc = f"""BEGIN:VCARD
VERSION:3.0
N:{a['name']}
FN:{a['name']}
ORG:{a['company']}
TITLE:{a['role']}
TEL;TYPE=CELL:{a['phone_mobile']}
TEL;TYPE=WORK:{a['phone_office']}
EMAIL:{a['emails']}
END:VCARD
"""

    return vc, 200, {
        "Content-Type": "text/vcard",
        "Content-Disposition": f"attachment; filename={slug}.vcf"
    }


# ---------------------------
# QR CODE PNG
# ---------------------------
@app.route("/qr/<slug>.png")
def qr_png(slug):
    url = f"{BASE_URL}/card/{slug}"
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read(), 200, {"Content-Type": "image/png"}


# ---------------------------
# STATIC UPLOAD SERVER
# ---------------------------
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory("static/uploads", filename)


# ---------------------------
# WAITRESS PER RENDER
# ---------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
