from io import BytesIO
import qrcode
from flask import send_file, abort

# --- helper: trova agente ignorando maiuscole/minuscole
def find_agent_by_slug(slug: str):
    s = (slug or "").strip()
    db = get_db()
    row = db.execute("SELECT * FROM agents WHERE slug = ?", (s,)).fetchone()
    if not row:
        row = db.execute("SELECT * FROM agents WHERE lower(slug) = lower(?)", (s,)).fetchone()
    return row

def make_qr_png(url: str) -> BytesIO:
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# --- accetta sia /qr/<slug> sia /qr/<slug>.png
@app.get("/qr/<slug>")
@app.get("/qr/<slug>.png")
def qr_personal(slug):
    agent = find_agent_by_slug(slug)
    if not agent:
        abort(404)
    base = BASE_URL.rstrip("/")
    url  = f"{base}/{agent['slug']}"
    png  = make_qr_png(url)
    # invia sempre un PNG
    return send_file(png, mimetype="image/png",
                     download_name=f"{agent['slug']}.png")
