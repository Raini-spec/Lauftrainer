import streamlit as st
import requests
from google import genai
import time
from datetime import datetime
import PyPDF2
import extra_streamlit_components as stx
import json
from PIL import Image
import os

st.set_page_config(page_title="KI Trainer", layout="centered")

# --- COOKIE MANAGER ---
cookie_manager = stx.CookieManager()
st.write("") 

st.title("🏃‍♂️🚴 KI Trainer: Strava & Gemini")
st.caption("🔒 **Version 4.19** – Multi-User Ready (Individuelle Plan-Speicherung)")

# --- STATUS-VARIABLEN ---
if "messages" not in st.session_state: st.session_state.messages = []
if "strava_context" not in st.session_state: st.session_state.strava_context = ""
if "daten_geladen" not in st.session_state: st.session_state.daten_geladen = False
if "doc_names" not in st.session_state: st.session_state.doc_names = []
if "doc_texts" not in st.session_state: st.session_state.doc_texts = []
if "doc_images" not in st.session_state: st.session_state.doc_images = []

# --- DATEN AUS COOKIES LADEN ---
auth_cookie = cookie_manager.get("auth_paket")
auth_data = json.loads(auth_cookie) if isinstance(auth_cookie, str) else (auth_cookie or {})
if "temp_auth_data" in st.session_state: auth_data = st.session_state.temp_auth_data

physio_cookie = cookie_manager.get("physio_paket")
physio_data = json.loads(physio_cookie) if isinstance(physio_cookie, str) else (physio_cookie or {})

# --- HILFSFUNKTIONEN ---
def get_plan_filename():
    cid = auth_data.get("client_id", "default")
    return f"plan_{cid}.txt"

def get_valid_strava_token():
    global auth_data
    expires_at = auth_data.get("expires_at")
    if not expires_at or time.time() > (float(expires_at) - 300):
        url = "https://www.strava.com/oauth/token"
        payload = {"client_id": auth_data.get("client_id"), "client_secret": auth_data.get("client_secret"), "refresh_token": auth_data.get("refresh_token"), "grant_type": "refresh_token"}
        res = requests.post(url, data=payload)
        if res.status_code == 200:
            data = res.json()
            auth_data.update({"access_token": data["access_token"], "refresh_token": data["refresh_token"], "expires_at": data["expires_at"]})
            cookie_manager.set("auth_paket", json.dumps(auth_data), key="cookie_refresh")
            return data["access_token"]
        return None
    return auth_data.get("access_token")

# --- PLAN LOKAL VOM SERVER LADEN ---
if "trainingsplan" not in st.session_state:
    filename = get_plan_filename()
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            st.session_state.trainingsplan = f.read()

# --- HAUPT-APP (LOGIN PRÜFUNG) ---
gemini_key = auth_data.get("gemini_key")
if not gemini_key or not auth_data.get("access_token"):
    st.info("👋 Bitte einloggen oder App manuell einrichten.")
    # ... (hier steht dein bisheriger Login-Code aus Version 4.18) ...
else:
    client = genai.Client(api_key=gemini_key)
    # ... (Rest der App ab Zeile "HAUPT-APP" wie gewohnt, 
    # aber nutze in den Button-Funktionen für "Neuen Plan" und "Aktualisieren" 
    # beim Speichern IMMER: open(get_plan_filename(), "w", ...) ) ...
