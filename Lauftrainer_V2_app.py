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
st.caption("🔒 **Version 4.18** – Finale, stabile Version (Server-Speicher & Error-Handling)")

# --- STATUS-VARIABLEN ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "strava_context" not in st.session_state:
    st.session_state.strava_context = ""
if "daten_geladen" not in st.session_state:
    st.session_state.daten_geladen = False

# Listen für mehrere Dokumente/Bilder
if "doc_names" not in st.session_state:
    st.session_state.doc_names = []
if "doc_texts" not in st.session_state:
    st.session_state.doc_texts = []
if "doc_images" not in st.session_state:
    st.session_state.doc_images = []

# --- DATEN AUS DEM "PAKET"-COOKIE LESEN ---
auth_cookie = cookie_manager.get("auth_paket")
auth_data = {}
if auth_cookie:
    try:
        auth_data = json.loads(auth_cookie) if isinstance(auth_cookie, str) else auth_cookie
        if "temp_auth_data" in st.session_state:
            del st.session_state.temp_auth_data
    except:
        pass

if "temp_auth_data" in st.session_state:
    auth_data = st.session_state.temp_auth_data

physio_cookie = cookie_manager.get("physio_paket")
physio_data = {}
if physio_cookie:
    try:
        physio_data = json.loads(physio_cookie) if isinstance(physio_cookie, str) else physio_cookie
    except:
        pass

# --- PLAN LOKAL VOM SERVER LADEN ---
if "trainingsplan" not in st.session_state:
    if os.path.exists("mein_plan.txt"):
        try:
            with open("mein_plan.txt", "r", encoding="utf-8") as f:
                plan_inhalt = f.read()
                if plan_inhalt.strip():  # Nur laden, wenn die Datei nicht leer ist
                    st.session_state.trainingsplan = plan_inhalt
        except Exception:
            pass

gemini_key = auth_data.get("gemini_key")
client_id = auth_data.get("client_id")
client_secret = auth_data.get("client_secret")
access_token = auth_data.get("access_token")
refresh_token = auth_data.get("refresh_token")
expires_at = auth_data.get("expires_at")

trainer_instructions = physio_data.get("instructions", "")
vo2max = physio_data.get("vo2max", "")
laktatschwelle = physio_data.get("laktat", "")
belastung = physio_data.get("belastung", "")

def get_valid_strava_token():
    global access_token, refresh_token, expires_at, auth_data
    if not expires_at or time.time() > (float(expires_at) - 300):
        with st.spinner("Erneuere Strava-Zugriff..."):
            url = "https://www.strava.com/oauth/token"
            payload = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            }
            res = requests.post(url, data=payload)
            if res.status_code == 200:
                data = res.json()
                access_token = data["access_token"]
                auth_data["access_token"] = access_token
                auth_data["refresh_token"] = data["refresh_token"]
                auth_data["expires_at"] = data["expires_at"]
                cookie_manager.set("auth_paket", json.dumps(auth_data), key="cookie_set_refresh")
            else:
                st.error("Token-Refresh fehlgeschlagen.")
                return None
    return access_token

# --- LOGIN-BEREICH ---
if not gemini_key or not access_token:
    st.info("👋 Willkommen! Wähle eine Methode, um deine App zu starten.")
    tab1, tab2 = st.tabs(["📁 Schneller Login (Datei + Passwort)", "⌨️ Manuelle Einrichtung"])
    with tab1:
        config_file = st.file_uploader("📥 Konfigurations-Datei (.json) hochladen", type=["json"], key="upload_tab1")
        master_pw = st.text_input("🔑 Master-Passwort eingeben", type="password", key="pw_tab1")
        if st.button("🔐 Entsperren & Einrichten", key="btn_tab1"):
            if config_file and master_pw:
                try:
                    content = json.load(config_file)
                    if content.get("master_pw") == master_pw:
                        st.session_state.temp_auth_data = content
                        st.rerun()
                    else:
                        st.error("Das eingegebene Passwort ist falsch.")
                except Exception as e:
                    st.error(f"Datei fehlerhaft: {e}")
    with tab2:
        in_pw = st.text_input("🔑 Wähle dein Master-Passwort", type="password", key="setup_pw")
        in_gemini = st.text_input("1. Gemini API Key", type="password", key="setup_gemini")
        in_client_id = st.text_input("2. Strava Client-ID", key="setup_id")
        in_client_secret = st.text_input("3. Geheimer Clientschlüssel", type="password", key="setup_secret")
        if in_client_id:
            auth_url = f"https://www.strava.com/oauth/authorize?client_id={in_client_id}&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=activity:read_all"
            st.markdown(f"[👉 Klicke hier, um Strava freizugeben (WICHTIG!)]({auth_url})")
        in_code = st.text_input("4. Kopiere den Code aus der Adresszeile hier hinein", key="setup_code")
        if st.button("🚀 App aktivieren", key="btn_setup"):
            if in_pw and in_gemini and in_client_id and in_client_secret and in_code:
                url = "https://www.strava.com/oauth/token"
                payload = {"client_id": in_client_id, "client_secret": in_client_secret, "code": in_code, "grant_type": "authorization_code"}
                res = requests.post(url, data=payload)
                if res.status_code == 200:
                    res_data = res.json()
                    neues_paket = {
                        "master_pw": in_pw, "gemini_key": in_gemini, "client_id": in_client_id, 
                        "client_secret": in_client_secret, "access_token": res_data["access_token"], 
                        "refresh_token": res_data["refresh_token"], "expires_at": res_data["expires_at"]
                    }
                    st.session_state.pending_auth = neues_paket
                    st.session_state["auto_config_json"] = json.dumps(neues_paket, indent=2)
                    st.success("App konfiguriert!")
            else:
                st.error("Bitte fülle alle Felder aus!")
        if "auto_config_json" in st.session_state:
            st.download_button("📥 JETZT DEINE CONFIG.JSON HERUNTERLADEN", data=st.session_state["auto_config_json"], file_name="config.json", mime="application/json", key="btn_down_auto")
            if st.button("🔄 App starten", key="btn_start_after_setup"):
                if "pending_auth" in st.session_state: st.session_state.temp_auth_data = st.session_state.pending_auth
                st.rerun()

# --- HAUPT-APP ---
else:
    # API Client global für alle Chat/Plan-Funktionen initialisieren
    client = genai.Client(api_key=gemini_key)

    if "temp_auth_data" in st.session_state:
        cookie_manager.set("auth_paket", json.dumps(st.session_state.temp_auth_data), key="cookie_set_main_auth")

    if st.sidebar.button("⚠️ Lokale Daten löschen", key="btn_clear_device_data"):
        cookie_manager.delete("auth_paket", key="cookie_del_auth")
        cookie_manager.delete("physio_paket", key="cookie_del_physio")
        
        # Plan restlos vom Server wischen
        if os.path.exists("mein_plan.txt"):
            os.remove("mein_plan.txt")
            
        for key in ["messages", "strava_context", "daten_geladen", "doc_names", "doc_texts", "doc_images", "temp_auth_data", "pending_auth", "auto_config_json", "heute_plan", "woche_plan", "trainingsplan", "upload_knowledge_files"]:
            if key in st.session_state: del st.session_state[key]
        time.sleep(0.5)
        st.rerun()

    with st.expander("🧠 Trainer-Instruktionen"):
        new_instructions = st.text_area("Anweisungen", value=trainer_instructions, height=150, key="input_instructions")
        if st.button("💾 Speichern", key="btn_save_instructions"):
            physio_data["instructions"] = new_instructions
            cookie_manager.set("physio_paket", json.dumps(physio_data), key="cookie_set_instructions")
            st.success("Gespeichert!")

    with st.expander("📊 Physiologische Werte"):
        col_v, col_l, col_b = st.columns(3)
        with col_v: new_vo2max = st.text_input("VO2max", value=vo2max, key="input_vo2max")
        with col_l: new_laktat = st.text_input("Laktatschwelle", value=laktatschwelle, key="input_laktat")
        with col_b: new_belastung = st.text_input("Aktuelle Belastung", value=belastung, key="input_belastung")
        if st.button("💾 Werte speichern", key="btn_save_physio"):
            physio_data.update({"vo2max": new_vo2max, "laktat": new_laktat, "belastung": new_belastung})
            cookie_manager.set("physio_paket", json.dumps(physio_data), key="cookie_set_physio_values")
            st.success("Gespeichert!")

    with st.expander("📄 Hintergrundwissen (Dateien) verwalten"):
        uploaded_files = st.file_uploader("Dateien hochladen", type=["txt", "md", "pdf", "png", "jpg", "jpeg"], accept_multiple_files=True, key="upload_knowledge_files")
        st.session_state.doc_names, st.session_state.doc_texts, st.session_state.doc_images = [], [], []
        if uploaded_files:
            for f in uploaded_files[:5]:
                st.session_state.doc_names.append(f.name)
                if f.name.lower().endswith(('.png', '.jpg', '.jpeg')): st.session_state.doc_images.append(Image.open(f))
                elif f.name.lower().endswith(".pdf"):
                    text = ""
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages: text += page.extract_text() + "\n"
                    st.session_state.doc_texts.append(text)
                else: st.session_state.doc_texts.append(f.read().decode("utf-8"))
            st.success(f"Geladen: {len(st.session_state.doc_names)} Dateien.")

    with st.expander("📅 Aktueller Trainingsplan", expanded=bool(st.session_state.get("trainingsplan"))):
        if st.session_state.get("trainingsplan"):
            st.markdown(st.session_state.trainingsplan)
            st.divider()
            col_md, col_txt = st.columns(2)
            with col_md:
                st.download_button("📥 Als Markdown (.md) speichern", data=st.session_state.trainingsplan, file_name="trainingsplan.md", mime="text/markdown", key="dl_md")
            with col_txt:
                st.download_button("📥 Als Textdatei (.txt) speichern", data=st.session_state.trainingsplan, file_name="trainingsplan.txt", mime="text/plain", key="dl_txt")
        else:
            st.info("Es ist noch kein Trainingsplan vorhanden. Lade unten deine Strava-Daten und erstelle deinen ersten Plan!")

    st.divider()
    
    st.subheader("🎯 1. Daten abrufen")
    if st.button("⬇️ Strava-Daten laden", key="btn_load_strava"):
        strava_token = get_valid_strava_token()
        if strava_token:
            with st.spinner("Lade Daten von Strava..."):
                try:
                    response = requests.get(f"https://www.strava.com/api/v3/athlete/activities?per_page=30", headers={"Authorization": f"Bearer {strava_token}"})
                    if response.status_code == 200:
                        activities = response.json()
                        if activities:
                            data = ""
                            for act in activities:
                                t = act.get('sport_type', act.get('type', 'Unbekannt'))
                                d = act.get('distance', 0) / 1000
                                s = act.get('average_speed', 0)
                                date = act.get('start_date_local', '')[:10]
                                p = act.get('average_heartrate', 'Kein Puls')
                                info = f"Pace: {(1000/s)/60:.2f} min/km" if t in ["Run", "Lauf"] and s > 0 else f"Geschw.: {s*3.6:.2f} km/h"
                                data += f"- [{date}] [{t}] {act.get('name')}: {d:.2f} km | {info} | Ø Puls: {p}\n"
                            st.session_state.strava_context = data
                            st.session_state.daten_geladen = True
                            st.success("Daten erfolgreich geladen!")
                        else:
                            st.warning("Strava hat geantwortet, aber es wurden keine Aktivitäten in deinem Account gefunden.")
                    else:
                        st.error(f"Fehler beim Abrufen der Strava-Daten. Statuscode: {response.status_code}")
                except Exception as e:
                    st.error(f"Netzwerk- oder Verbindungsfehler: {e}")

    if st.session_state.get("daten_geladen"):
        st.subheader("🗓️ 2. Trainingsplan steuern")
        col1, col2 = st.columns(2)
        if col1.button("✨ Neuen Plan erstellen", key="btn_new_plan"):
            with st.spinner("Erstelle neuen Plan..."):
                prompt = f"Erstelle einen neuen Trainingsplan.\nHistorie:\n{st.session_state.strava_context}\nInstruktionen: {trainer_instructions}\n"
                if vo2max or laktatschwelle or belastung:
                    prompt += f"\nPhysiologie: VO2max:{vo2max}, Laktat:{laktatschwelle}, Belastung:{belastung}\n"
                req = [prompt] + st.session_state.doc_images
                try:
                    resp = client.models.generate_content(model='gemini-2.5-flash', contents=req)
                    if resp.text:
                        st.session_state.trainingsplan = resp.text
                        with open("mein_plan.txt", "w", encoding="utf-8") as f:
                            f.write(resp.text)
                        st.rerun()
                    else:
                        st.error("Die KI hat ein leeres Ergebnis zurückgegeben. Bitte noch einmal klicken.")
                except Exception as e: st.error(f"Generierungsfehler: {e}")
        
        if st.session_state.get("trainingsplan"):
            if col2.button("🔄 Plan aktualisieren", key="btn_update_plan"):
                with st.spinner("Passe Plan an..."):
                    prompt = f"Hier ist mein alter Plan:\n{st.session_state.trainingsplan}\n\nHier sind neue Trainingsdaten:\n{st.session_state.strava_context}\n\nAktualisiere den Plan intelligent."
                    if vo2max or laktatschwelle or belastung:
                        prompt += f"\nPhysiologie: VO2max:{vo2max}, Laktat:{laktatschwelle}, Belastung:{belastung}\n"
                    req = [prompt] + st.session_state.doc_images
                    try:
                        resp = client.models.generate_content(model='gemini-2.5-flash', contents=req)
                        if resp.text:
                            st.session_state.trainingsplan = resp.text
                            with open("mein_plan.txt", "w", encoding="utf-8") as f:
                                f.write(resp.text)
                            st.rerun()
                        else:
                            st.error("Die KI hat ein leeres Ergebnis zurückgegeben. Bitte noch einmal klicken.")
                    except Exception as e: st.error(f"Generierungsfehler: {e}")

    # --- SCHNELL-CHECK ---
    if st.session_state.get("trainingsplan"):
        st.divider()
        st.subheader("⚡ Coach Schnell-Check")
        c1, c2 = st.columns(2)
        if c1.button("🚀 Training heute", key="btn_check_today"):
            with st.spinner("Analysiere heute..."):
                req = [f"Gib mir nur für HEUTE ein Training basierend auf:\n{st.session_state.trainingsplan}\nStrava-Daten:\n{st.session_state.get('strava_context', 'Keine neuen geladen.')}"] + st.session_state.doc_images
                try:
                    resp = client.models.generate_content(model='gemini-2.5-flash', contents=req)
                    if resp.text: st.write(resp.text)
                except Exception as e:
                    st.error(f"Fehler: {e}")
                    
        if c2.button("📅 Wochenplan Zusammenfassung", key="btn_check_week"):
            with st.spinner("Analysiere Woche..."):
                req = [f"Gib mir eine kompakte Zusammenfassung des Trainings für die nächsten 7 Tage basierend auf:\n{st.session_state.trainingsplan}"] + st.session_state.doc_images
                try:
                    resp = client.models.generate_content(model='gemini-2.5-flash', contents=req)
                    if resp.text: st.write(resp.text)
                except Exception as e:
                    st.error(f"Fehler: {e}")

    st.divider()
    st.subheader("💬 Chat mit Coach")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if user_input := st.chat_input("Nachricht an den Coach...", key="input_chat"):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"): st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Tippt..."):
                prompt = f"Du bist Coach. Plan:\n{st.session_state.get('trainingsplan')}\nDaten:\n{st.session_state.strava_context}\nFrage: {user_input}"
                req = [prompt] + st.session_state.doc_images
                try:
                    resp = client.models.generate_content(model='gemini-2.5-flash', contents=req)
                    if resp.text:
                        st.markdown(resp.text)
                        st.session_state.messages.append({"role": "assistant", "content": resp.text})
                except Exception as e:
                    st.error(f"Fehler: {e}")
