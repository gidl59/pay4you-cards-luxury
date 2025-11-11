import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from io import BytesIO
import qrcode

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "devkey123")

# DB locale
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///agents.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

ADMIN_PASS = os.environ.get("ADMIN_PASS", "changeme")


# ---------------------------------------
# MODEL
# ---------------------------------------
class Agent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    phone_mobile = db.Column(db.String(40), nullable=True)
    phone_office = db.Column(db.String(40), nullable=True)
    websites = db.Column(db.String(200), nullable=True)
    email = db.Column(db.String(120), nullable=True)


@app.before_request
def create_db_if_needed():
    db.create_all()


# ---------------------------------------
# LOGIN
# ---------------------------------------
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
    session.clear()
    return redirect(url_for("login"))


def require_admin():
    if not session.get("admin"):
        return redirect(url_for("login"))


# ---------------------------------------
# ADMIN HOME
# ---------------------------------------
@app.route("/admin")
def admin_home():
    if not session.get("admin"):
        return redirect(url_for("login"))
    agents = Agent.query.all()
    return render_template("admin_list.html", agents=agents)


@app.route("/admin/new", methods=["GET", "POST"])
def admin_new():
    if not session.get("admin"):
        return redirect(url_for("login"))
    if request.method == "POST":
        a = Agent(
            name=request.form["name"],
            slug=request.form["slug"].lower().strip(),
            phone_mobile=request.form.get("phone_mobile"),
            phone_office=request.form.get("phone_office"),
            websites=request.form.get("websites"),
            email=request.form.get("email")
        )
        db.session.add(a)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Slug già esistente", "error")
        return redirect(url_for("admin_home"))
    return render_template("admin_edit.html", agent=None)


@app.route("/admin/edit/<slug>", methods=["GET", "POST"])
def admin_edit(slug):
    if not session.get("admin"):
        return redirect(url_for("login"))

    agent = Agent.query.filter_by(slug=slug).first_or_404()

    if request.method == "POST":
        agent.name = request.form["name"]
        agent.slug = request.form["slug"].lower().strip()
        agent.phone_mobile = request.form.get("phone_mobile")
        agent.phone_office = request.form.get("phone_office")
        agent.websites = request.form.get("websites")
        agent.email = request.form.get("email")
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Slug già esistente", "error")
        return redirect(url_for("admin_home"))

    return render_template("admin_edit.html", agent=agent)


@app.route("/admin/delete/<slug>", methods=["POST"])
def admin_delete(slug):
    if not session.get("admin"):
        return redirect(url_for("login"))

    agent = Agent.query.filter_by(slug=slug).first_or_404()
    db.session.delete(agent)
    db.session.commit()
    return redirect(url_for("admin_home"))


# ---------------------------------------
# PAGINA PUBBLICA
# ---------------------------------------
@app.route("/card/<slug>")
def public_card(slug):
    agent = Agent.query.filter_by(slug=slug).first()
    if not agent:
        return render_template("404.html"), 404
    return render_template("public_card.html", agent=agent)


# ---------------------------------------
# QR
# ---------------------------------------
@app.route("/qr/<slug>.png")
def qr_png(slug):
    url = request.url_root.rstrip("/") + url_for("public_card", slug=slug)
    qr = qrcode.make(url)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# ---------------------------------------
# VCARD
# ---------------------------------------
@app.route("/vcard/<slug>.vcf")
def vcard(slug):
    agent = Agent.query.filter_by(slug=slug).first_or_404()
    card = f"""BEGIN:VCARD
VERSION:3.0
FN:{agent.name}
TEL;TYPE=CELL:{agent.phone_mobile or ""}
EMAIL:{agent.email or ""}
URL:{agent.websites or ""}
END:VCARD"""
    return app.response_class(card, mimetype="text/vcard")


# ---------------------------------------
# HEALTH
# ---------------------------------------
@app.route("/health")
def health():
    return "OK", 200


# ---------------------------------------
# MAIN
# ---------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
