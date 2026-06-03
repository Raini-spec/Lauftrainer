import streamlit as st
import requests
from google import genai
import json
import os
import time
from datetime import datetime
import PyPDF2
import pandas as pd

SECRETS_FILE = "secrets.json"

def load_secrets():
    if os.path.exists(SECRETS_FILE):
        with open(SECRETS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_secrets(data):
    with open(SECRETS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_valid_strava_token(secrets):
    if time.time() > (secrets.get("strava_expires_at", 0) - 300):
        with st.spinner("Erneuere Strava-Zugriff..."):
            url = "https://www.strava.com/oauth/token"
            payload = {
                "client_id": secrets["strava_client_id"],
                "client_secret": secrets["strava_client_secret"],
                "refresh_token": secrets["strava_refresh_token"],
                "grant_type": "refresh_token"
            }
            res = requests.post(url, data=payload)
            if res.status_code == 200:
                data = res.json()
                secrets["strava_access_token"] = data["access_token"]
                secrets["strava_refresh_token"] = data["refresh_token"]
                secrets["strava_expires_at"] = data["expires_at"]
                save_secrets(secrets)
            else:
                st.error("Token-Refresh fehlgeschlagen.")
                return None
    return secrets["strava_access_token"]

st.set_page_config(page_title="KI Trainer", layout="centered")
st.title("🏃‍♂️🚴 KI Trainer: Strava & Gemini")

secrets = load_secrets()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "strava_context" not in st.session_state:
    st.session_state.strava_context = ""
if "daten_geladen" not in st.session_state:
    st.session_state.daten_geladen = False
if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()

if not secrets:
    st.info("👋 Willkommen! Richten wir deine App einmalig ein.")
    gemini_key = st.text_input("1. Gemini API Key", type="password")
    client_id = st.text_input("2. Strava Client-ID")
    client_secret = st.text_input("3. Geheimer Clientschlüssel", type="password")
    
    if client_id:
        auth_url = f"https://www.strava.com/oauth/authorize?client_id={client_id}&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=activity:read_all"
        st.markdown(f"[👉 Klicke hier, um Strava freizugeben]({auth_url})")
    
    auth_code = st.text_input("5. Kopiere den Code aus der Adresszeile hier hinein")
    
    if st.button("Aktivieren"):
        url = "https://www.strava.com/oauth/token"
        payload = {"client_id": client_id, "client_secret": client_secret, "code": auth_code, "grant_type": "authorization_code"}
        res = requests.post(url, data=payload)
        if res.status_code == 200:
            res_data = res.json()
            initial_secrets = {
                "gemini_api_key": gemini_key,
                "strava_client_id": client_id,
                "strava_client_secret": client_secret,
                "strava_refresh_token": res_data["refresh_token"],
                "strava_access_token": res_data["access_token"],
                "strava_expires_at": res_data["expires_at"]
            }
            save_secrets(initial_secrets)
            st.success("Erfolgreich! Lade die Seite neu.")

else:
    # --- SIDEBAR ELEMENTE ---
    if st.sidebar.button("⚠️ Alle Keys löschen"):
        os.remove(SECRETS_FILE)
        st.rerun()

    if st.session_state.get("daten_geladen", False) and not st.session_state.df.empty:
        with st.sidebar.expander("📈 Trainings-Statistiken"):
            df = st.session_state.df.copy()
            df["Datum"] = pd.to_datetime(df["Datum"])
            df = df.sort_values("Datum")
            
            sportarten = df["Sportart"].unique()
            gewaehlte_sportart = st.multiselect("Sportart filtern:", sportarten, default=sportarten)
            df_filtered = df[df["Sportart"].isin(gewaehlte_sportart)]
            
            if not df_filtered.empty:
                tab1, tab2, tab3 = st.tabs(["🛣️ Volumen", "⏱️ Leistung", "🔥 Energie"])
                
                with tab1:
                    st.bar_chart(df_filtered.set_index("Datum")["Distanz (km)"])
                with tab2:
                    st.line_chart(df_filtered.set_index("Datum")[["Puls", "Pace (min/km)"]].dropna(how="all"))
                with tab3:
                    st.bar_chart(df_filtered.set_index("Datum")["Kalorien"])
    # ------------------------

    with st.expander("🧠 Trainer-Instruktionen bearbeiten"):
        trainer_instructions = st.text_area("Anweisungen", value=secrets.get("trainer_instructions", ""), height=150)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Instruktionen Speichern"):
                secrets["trainer_instructions"] = trainer_instructions
                save_secrets(secrets)
                st.success("Gespeichert!")
        with col2:
            if st.button("🗑️ Instruktionen Löschen"):
                secrets["trainer_instructions"] = ""
                save_secrets(secrets)
                st.rerun()

    with st.expander("📊 Physiologische Werte (Garmin/Diagnostik)"):
        col1, col2 = st.columns(2)
        
        # Sicherstellen, dass der Index für die Selectbox gültig ist
        geschlecht_options = ["", "Männlich", "Weiblich", "Divers"]
        gespeichertes_geschlecht = secrets.get("geschlecht", "")
        geschlecht_index = geschlecht_options.index(gespeichertes_geschlecht) if gespeichertes_geschlecht in geschlecht_options else 0
        
        with col1:
            alter = st.text_input("Alter", value=secrets.get("alter", ""), placeholder="z.B. 35")
            geschlecht = st.selectbox("Geschlecht", geschlecht_options, index=geschlecht_index)
            ruhepuls = st.text_input("Ruhepuls", value=secrets.get("ruhepuls", ""), placeholder="z.B. 50")
            max_puls = st.text_input("Maximalpuls", value=secrets.get("max_puls", ""), placeholder="z.B. 190")
        with col2:
            vo2max = st.text_input("VO2max", value=secrets.get("vo2max", ""), placeholder="z.B. 52")
            laktatschwelle = st.text_input("Laktatschwelle", value=secrets.get("laktatschwelle", ""), placeholder="z.B. 165 bpm")
            belastung = st.text_input("Aktuelle Belastung", value=secrets.get("belastung", ""), placeholder="z.B. 850")
            
        if st.button("💾 Werte speichern"):
            secrets["alter"] = alter
            secrets["geschlecht"] = geschlecht
            secrets["ruhepuls"] = ruhepuls
            secrets["max_puls"] = max_puls
            secrets["vo2max"] = vo2max
            secrets["laktatschwelle"] = laktatschwelle
            secrets["belastung"] = belastung
            save_secrets(secrets)
            st.success("Werte gespeichert!")

    with st.expander("📄 Hintergrundwissen (PDF/TXT) verwalten"):
        if secrets.get("doc_name"):
            st.info(f"**Aktives Dokument:** {secrets['doc_name']}")
            if st.button("🗑️ Dokument entfernen"):
                secrets["doc_name"] = ""
                secrets["doc_text"] = ""
                save_secrets(secrets)
                st.rerun()
        else:
            uploaded_file = st.file_uploader("Datei hochladen", type=["txt", "md", "pdf"])
            if uploaded_file:
                text = ""
                if uploaded_file.name.endswith(".pdf"):
                    reader = PyPDF2.PdfReader(uploaded_file)
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                else:
                    text = uploaded_file.read().decode("utf-8")
                
                secrets["doc_name"] = uploaded_file.name
                secrets["doc_text"] = text
                save_secrets(secrets)
                st.success("Gespeichert!")
                st.rerun()

    anzahl_aktivitaeten = st.slider("Historie (Anzahl Aktivitäten)", 5, 50, 30)

    if st.button("🚀 Neue Strava-Daten laden & analysieren"):
        strava_token = get_valid_strava_token(secrets)
        if strava_token:
            with st.spinner("Lade Daten..."):
                response = requests.get(f"https://www.strava.com/api/v3/athlete/activities?per_page={anzahl_aktivitaeten}", headers={"Authorization": f"Bearer {strava_token}"})
                
                if response.status_code == 200:
                    activities = response.json()
                    aktivitaets_daten = ""
                    raw_data = [] 
                    
                    for act in activities:
                        typ = act.get('sport_type', act.get('type', 'Unbekannt'))
                        dist_km = act.get('distance', 0) / 1000
                        speed = act.get('average_speed', 0)
                        start = act.get('start_date_local', '')[:10]
                        puls = act.get('average_heartrate', None)
                        kalorien = act.get('calories', act.get('kilojoules', 0))
                        
                        pace = None
                        if typ in ["Run", "Hike", "Lauf", "Wanderung"]:
                            if speed > 0:
                                pace = (1000 / speed) / 60
                            info = f"Pace: {pace:.2f} min/km" if pace else "Pace: 0"
                        else:
                            info = f"Geschw.: {speed * 3.6:.2f} km/h"
                            
                        aktivitaets_daten += f"- [{start}] [{typ}] {act.get('name')}: {dist_km:.2f} km | {info} | Ø Puls: {puls if puls else 'Kein Puls'}\n"
                        
                        raw_data.append({
                            "Datum": start,
                            "Sportart": typ,
                            "Distanz (km)": dist_km,
                            "Pace (min/km)": pace,
                            "Puls": puls,
                            "Kalorien": kalorien
                        })
                    
                    st.session_state.strava_context = aktivitaets_daten
                    st.session_state.df = pd.DataFrame(raw_data)
                    st.session_state.messages = [] 
                    st.session_state.daten_geladen = True
                    
                    with st.spinner("KI analysiert..."):
                        client = genai.Client(api_key=secrets["gemini_api_key"])
                        heute = datetime.now().strftime('%Y-%m-%d')
                        prompt = f"""Analysiere diesen Trainingsverlauf präzise. 
                        WICHTIG: Heute ist der {heute}. Berechne im Hintergrund zwingend die exakte Anzahl der Tage zwischen der neuesten Aktivität und heute, bevor du eine Trainingspause bewertest!
                        
                        Historie:\n{aktivitaets_daten}\n"""
                        
                        if secrets.get("trainer_instructions"):
                            prompt += f"\nAnweisungen:\n{secrets['trainer_instructions']}"
                        if secrets.get("doc_text"):
                            prompt += f"\nHintergrunddaten:\n{secrets['doc_text']}"
                            
                        if any([secrets.get(k) for k in ["alter", "geschlecht", "ruhepuls", "max_puls", "vo2max", "laktatschwelle", "belastung"]]):
                            prompt += "\nPhysiologische Kennwerte:\n"
                            if secrets.get("alter"): prompt += f"- Alter: {secrets['alter']}\n"
                            if secrets.get("geschlecht"): prompt += f"- Geschlecht: {secrets['geschlecht']}\n"
                            if secrets.get("ruhepuls"): prompt += f"- Ruhepuls: {secrets['ruhepuls']}\n"
                            if secrets.get("max_puls"): prompt += f"- Maximalpuls: {secrets['max_puls']}\n"
                            if secrets.get("vo2max"): prompt += f"- VO2max: {secrets['vo2max']}\n"
                            if secrets.get("laktatschwelle"): prompt += f"- Laktatschwelle: {secrets['laktatschwelle']}\n"
                            if secrets.get("belastung"): prompt += f"- Aktuelle Belastung: {secrets['belastung']}\n"
                            
                        antwort = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                        st.session_state.messages.append({"role": "assistant", "content": antwort.text})
                else:
                    st.error("Fehler bei Strava-Abfrage.")

    st.divider()

    st.subheader("💬 Chat mit deinem Coach")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if st.session_state.get("daten_geladen", False): 
        if user_input := st.chat_input("Tippe deine Nachricht an den Coach..."):
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)
                
            with st.chat_message("assistant"):
                with st.spinner("Tippt..."):
                    client = genai.Client(api_key=secrets["gemini_api_key"])
                    history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                    heute = datetime.now().strftime('%Y-%m-%d')
                    
                    sys_prompt = f"""
                    Du bist ein Ausdauer-Coach. Heute ist der {heute}. Beantworte die Nachricht.
                    Trainingsdaten:\n{st.session_state.strava_context}
                    Hintergrund:\n{secrets.get('doc_text', '')}
                    Instruktionen:\n{secrets.get('trainer_instructions', '')}
                    
                    Physiologische Kennwerte:
                    Alter: {secrets.get('alter', 'Nicht angegeben')}
                    Geschlecht: {secrets.get('geschlecht', 'Nicht angegeben')}
                    Ruhepuls: {secrets.get('ruhepuls', 'Nicht angegeben')}
                    Maximalpuls: {secrets.get('max_puls', 'Nicht angegeben')}
                    VO2max: {secrets.get('vo2max', 'Nicht angegeben')}
                    Laktatschwelle: {secrets.get('laktatschwelle', 'Nicht angegeben')}
                    Aktuelle Belastung: {secrets.get('belastung', 'Nicht angegeben')}
                    
                    Bisheriger Chat:
                    {history}
                    """
                    
                    antwort = client.models.generate_content(model='gemini-2.5-flash', contents=sys_prompt)
                    st.markdown(antwort.text)
                    st.session_state.messages.append({"role": "assistant", "content": antwort.text})
