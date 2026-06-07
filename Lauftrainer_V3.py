import streamlit as st
import requests
from google import genai
import time
from datetime import datetime
import PyPDF2
import extra_streamlit_components as stx

st.set_page_config(page_title="KI Trainer", layout="centered")

# --- COOKIE MANAGER INITIALISIEREN ---
@st.cache_resource
def get_manager():
    return stx.CookieManager()
cookie_manager = get_manager()
st.write("") # Wichtig, damit Cookies geladen werden

st.title("🏃‍♂️🚴 KI Trainer: Strava & Gemini")
st.caption("🔒 **Version 3.0** – Sicherer lokaler Speicher")

# --- STATUS-VARIABLEN (für PDF & Chat, nur temporär pro Sitzung) ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "strava_context" not in st.session_state:
    st.session_state.strava_context = ""
if "daten_geladen" not in st.session_state:
    st.session_state.daten_geladen = False
if "doc_name" not in st.session_state:
    st.session_state.doc_name = ""
if "doc_text" not in st.session_state:
    st.session_state.doc_text = ""

# --- DATEN AUS LOKALEN COOKIES LESEN ---
gemini_key = cookie_manager.get("gemini_key")
client_id = cookie_manager.get("strava_client_id")
client_secret = cookie_manager.get("strava_client_secret")
access_token = cookie_manager.get("strava_access_token")
refresh_token = cookie_manager.get("strava_refresh_token")
expires_at = cookie_manager.get("strava_expires_at")

trainer_instructions = cookie_manager.get("trainer_instructions") or ""
vo2max = cookie_manager.get("vo2max") or ""
laktatschwelle = cookie_manager.get("laktatschwelle") or ""
belastung = cookie_manager.get("belastung") or ""

def get_valid_strava_token():
    global access_token, refresh_token, expires_at
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
                refresh_token = data["refresh_token"]
                expires_at = data["expires_at"]
                cookie_manager.set("strava_access_token", access_token)
                cookie_manager.set("strava_refresh_token", refresh_token)
                cookie_manager.set("strava_expires_at", str(expires_at))
            else:
                st.error("Token-Refresh fehlgeschlagen.")
                return None
    return access_token

# --- LOGIN (Wenn keine Cookies auf dem Gerät gefunden werden) ---
if not gemini_key or not access_token:
    st.info("👋 Willkommen! Richten wir deine App einmalig auf diesem Gerät ein.")
    input_gemini = st.text_input("1. Gemini API Key", type="password")
    input_client_id = st.text_input("2. Strava Client-ID")
    input_client_secret = st.text_input("3. Geheimer Clientschlüssel", type="password")
    
    if input_client_id:
        auth_url = f"https://www.strava.com/oauth/authorize?client_id={input_client_id}&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=activity:read_all"
        st.markdown(f"[👉 Klicke hier, um Strava freizugeben]({auth_url})")
    
    auth_code = st.text_input("5. Kopiere den Code aus der Adresszeile hier hinein")
    
    if st.button("Aktivieren & Lokal Speichern"):
        url = "https://www.strava.com/oauth/token"
        payload = {"client_id": input_client_id, "client_secret": input_client_secret, "code": auth_code, "grant_type": "authorization_code"}
        res = requests.post(url, data=payload)
        if res.status_code == 200:
            res_data = res.json()
            cookie_manager.set("gemini_key", input_gemini)
            cookie_manager.set("strava_client_id", input_client_id)
            cookie_manager.set("strava_client_secret", input_client_secret)
            cookie_manager.set("strava_access_token", res_data["access_token"])
            cookie_manager.set("strava_refresh_token", res_data["refresh_token"])
            cookie_manager.set("strava_expires_at", str(res_data["expires_at"]))
            st.success("Erfolgreich! Lade die Seite neu.")
        else:
            st.error("Strava-Verbindung fehlgeschlagen.")

# --- HAUPT-APP ---
else:
    if st.sidebar.button("⚠️ Lokale Daten von diesem Gerät löschen"):
        cookie_manager.delete("gemini_key")
        cookie_manager.delete("strava_access_token")
        st.rerun()

    with st.expander("🧠 Trainer-Instruktionen bearbeiten"):
        new_instructions = st.text_area("Anweisungen", value=trainer_instructions, height=150)
        if st.button("💾 Instruktionen Lokal Speichern"):
            cookie_manager.set("trainer_instructions", new_instructions)
            st.success("Gespeichert!")

    with st.expander("📊 Physiologische Werte"):
        col_v, col_l, col_b = st.columns(3)
        with col_v:
            new_vo2max = st.text_input("VO2max", value=vo2max)
        with col_l:
            new_laktat = st.text_input("Laktatschwelle", value=laktatschwelle)
        with col_b:
            new_belastung = st.text_input("Aktuelle Belastung", value=belastung)
            
        if st.button("💾 Werte speichern"):
            cookie_manager.set("vo2max", new_vo2max)
            cookie_manager.set("laktatschwelle", new_laktat)
            cookie_manager.set("belastung", new_belastung)
            st.success("Werte lokal gespeichert!")

    with st.expander("📄 Hintergrundwissen (PDF) verwalten"):
        st.info("💡 PDFs müssen pro Sitzung neu geladen werden, da sie zu groß für den Handy-Speicher sind.")
        if st.session_state.doc_name:
            st.success(f"**Aktiv:** {st.session_state.doc_name}")
            if st.button("🗑️ Dokument entfernen"):
                st.session_state.doc_name = ""
                st.session_state.doc_text = ""
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
                
                st.session_state.doc_name = uploaded_file.name
                st.session_state.doc_text = text
                st.success("Temporär geladen!")
                st.rerun()

    anzahl_aktivitaeten = st.slider("Historie (Anzahl Aktivitäten)", 5, 50, 30)

    if st.button("🚀 Neue Strava-Daten laden & analysieren"):
        strava_token = get_valid_strava_token()
        if strava_token:
            with st.spinner("Lade Daten..."):
                response = requests.get(f"https://www.strava.com/api/v3/athlete/activities?per_page={anzahl_aktivitaeten}", headers={"Authorization": f"Bearer {strava_token}"})
                
                if response.status_code == 200:
                    activities = response.json()
                    aktivitaets_daten = ""
                    for act in activities:
                        typ = act.get('sport_type', act.get('type', 'Unbekannt'))
                        dist_km = act.get('distance', 0) / 1000
                        speed = act.get('average_speed', 0)
                        start = act.get('start_date_local', '')[:10]
                        puls = act.get('average_heartrate', 'Kein Puls')
                        
                        if typ in ["Run", "Hike", "Lauf", "Wanderung"]:
                            pace = (1000 / speed) / 60 if speed > 0 else 0
                            info = f"Pace: {pace:.2f} min/km"
                        else:
                            info = f"Geschw.: {speed * 3.6:.2f} km/h"
                            
                        aktivitaets_daten += f"- [{start}] [{typ}] {act.get('name')}: {dist_km:.2f} km | {info} | Ø Puls: {puls}\n"
                    
                    st.session_state.strava_context = aktivitaets_daten
                    st.session_state.messages = [] 
                    st.session_state.daten_geladen = True
                    
                    with st.spinner("KI analysiert..."):
                        client = genai.Client(api_key=gemini_key)
                        heute = datetime.now().strftime('%Y-%m-%d')
                        prompt = f"Analysiere diesen Trainingsverlauf präzise. Heute ist der {heute}.\nHistorie:\n{aktivitaets_daten}\n"
                        
                        if trainer_instructions: prompt += f"\nAnweisungen:\n{trainer_instructions}"
                        if st.session_state.doc_text: prompt += f"\nHintergrunddaten:\n{st.session_state.doc_text}"
                        if vo2max or laktatschwelle or belastung:
                            prompt += "\nPhysiologische Kennwerte:\n"
                            if vo2max: prompt += f"- VO2max: {vo2max}\n"
                            if laktatschwelle: prompt += f"- Laktatschwelle: {laktatschwelle}\n"
                            if belastung: prompt += f"- Aktuelle Belastung: {belastung}\n"
                            
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
                    client = genai.Client(api_key=gemini_key)
                    history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                    heute = datetime.now().strftime('%Y-%m-%d')
                    
                    sys_prompt = f"""
                    Du bist ein Ausdauer-Coach. Heute ist der {heute}. Beantworte die Nachricht.
                    Trainingsdaten:\n{st.session_state.strava_context}
                    Hintergrund:\n{st.session_state.doc_text}
                    Instruktionen:\n{trainer_instructions}
                    VO2max: {vo2max}
                    Laktatschwelle: {laktatschwelle}
                    Aktuelle Belastung: {belastung}
                    
                    Bisheriger Chat:
                    {history}
                    """
                    
                    antwort = client.models.generate_content(model='gemini-2.5-flash', contents=sys_prompt)
                    st.markdown(antwort.text)
                    st.session_state.messages.append({"role": "assistant", "content": antwort.text})
