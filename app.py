import os
import json
import sqlite3
from datetime import datetime
from io import BytesIO

from flask import (
    Flask, request, redirect, render_template, url_for,
    session, send_file, abort, flash
)
import qrcode

from google.cloud import storage
from google.oauth2 import service_account

# -------------------------------------------------
# CONFIGURAZIONE APP
# -------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET", "dev-secret")

DB_PATH = os.path.join(os.path.dirname(__file__), "agents.db")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "test")

# BASE_URL = URL del sito su Render, SENZA "/" finale
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000").rstrip("/")

# -------------------------------------------------
# CONFIGURAZIONE FIREBASE / GOOGLE CLOUD STORAGE
# (OPZIONALE, SOLO PER CARICAMENTO FOTO / PDF)
# -------------------------------------------------
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
FIREBASE_BUCKET = os.getenv("FIREBASE_BUCKET")
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON")

storage_client = None
bucket = None
if FIREBASE_PROJECT_ID and FIREBASE_BUCKET and FIREBASE_CREDENTIALS_JSON:
    try:
        creds_info = json.loads(FIREBASE_CREDENTIALS_JSON)
        credentials = service_account.Credentials.from_service_account_info(creds_info)
        storage_client = storage.Client(
            project=FIREBASE_PROJECT_ID, credentials=credentials
        )
        bucket = storage_client.bucket(FIREBASE_BUCKET)
    except Exception as e:
        print("Firebase storage init error:", e)
        storage_client = None
        bucket = None


# -------------------------------------------------
# DATABASE (sqlite)
# -------------------------------------------------
def init_db():
    """Crea la tabella agents se non esiste."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

