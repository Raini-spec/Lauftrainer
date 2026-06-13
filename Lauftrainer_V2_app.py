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
st.caption("🔒 **Version 4.20** – Dashboard in der Sidebar & Adaptiver Wochenplan")

# --- STATUS-VARIABLEN ---
if "messages" not in st.session_state: st.session_state.messages = []
if "strava_context" not in st.session_state: st.session_state.strava_context = ""
if "daten_geladen" not in st.session_state: st.session_state.daten_geladen = False
if "doc_names" not in st.session_state: st.session_state.doc_names = []
if "doc_texts" not in st.session_state: st.session_state.doc_texts = []
if "doc_images" not in st.session_state: st.session_state.doc_images = []

# --- DATEN AUS COOKIES LADEN ---
auth_cookie = cookie_manager.get("auth_paket")
auth_data = {}
if auth_cookie:
    try:
        auth_data = json.loads(auth_cookie) if isinstance(auth_cookie, str) else auth_cookie
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

# --- HILFSFUNKTIONEN FÜR MULTI-USER DATEIEN ---
def get_plan_filename():
    cid = auth_data.get("client_id", "default")
    return f"plan_{cid}.txt"

def get_woche_filename():
    cid = auth_data.get("client_id", "default")
    return f"woche_{cid}.txt"

def get_status_filename():
    cid = auth_data.get("client_id", "default")
    return f"status_{cid}.json"

def get_valid_strava_token():
    global auth_data
    expires_at = auth_data.get("expires_at")
    client_id = auth_data.get("client_id")
    client_secret = auth_data.get("client_secret")
    refresh_token = auth_data.get("refresh_token")
    
    if not expires_at or time.time() > (float(expires_at) - 300):
        with st.spinner("Erneuere Strava-Zugriff..."):
            url = "https://www.strava.com/oauth/token"
            payload = {"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token, "grant_type": "refresh_token"}
            res = requests.post(url, data=payload)
            if res.status_code == 200:
                data = res.json()
                auth_data["access_token"] = data["access_token"]
                auth_data["refresh_token"] = data["refresh_token"]
                auth_data["expires_at"] = data["expires_at"]
                cookie_manager.set("auth_paket", json.dumps(auth_data), key="cookie_set_refresh")
                return data["access_token"]
            else:
                st.error("Token-Refresh fehlgeschlagen.")
                return None
    return auth_data.get("access_token")

# --- DATEIEN VOM SERVER IN DEN SESSION STATE LADEN ---
if "trainingsplan" not in st.session_state:
    filename = get_plan_filename()
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                st.session_state.trainingsplan = f.read()
        except: pass

if "wochenplan" not in st.session_state:
    filename = get_woche_filename()
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                st.session_state.wochenplan = f.read()
        except: pass

if "leistungsstatus" not in st.session_state:
    filename = get_status_filename()
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                st.session_state.leistungsstatus = json.load(f)
        except: pass

gemini_key = auth_data.get("gemini_key")
access_token = auth_data.get("access_token")
trainer_instructions = physio_data.get("instructions", "")
vo2max = physio_data.get("vo2max", "")
laktatschwelle = physio_data.get("laktat", "")
belastung = physio_data.get("belastung", "")

# --- SEITENLEISTE (DAS ATHLETEN-DASHBOARD) ---
with st.sidebar:
    st.header("📊 Leistungszustand")
    if "leistungsstatus" in st.session_state:
        status = st.session_state.leistungsstatus
        st.caption(f"Letztes Update: {status.get('letztes_update', '---')}")
        st.metric("Geschätzter VO2max", f"⚡ {status.get('vo2max', '---')}")
        
        st.markdown("**🎯 Laufprognosen:**")
        st.markdown(f"• **5 km:** {status.get('prognose_5k', '---')}")
        st.markdown(f"• **10 km:** {status.get('prognose_10k', '---')}")
        st.markdown(f"• **21 km:** {status.get('prognose_21k', '---')}")
        
        st.markdown(f"🔥 **Belastung:**\n`{status.get('belastung', '---')}`")
    else:
        st.info("Noch kein Leistungsstatus berechnet. Lade deine Strava-Daten und aktualisiere den Wochenplan!")
        
    st.divider()
    st.header("👟 Letzte Aktivitäten")
    if "leistungsstatus" in st.session_state and st.session_state.leistungsstatus.get("letzte_aktivitaeten"):
        for act in st.session_state.leistungsstatus.get("letzte_aktivitaeten"):
            st.write(act)
    elif "last_three_activities" in st.session_state:
        for act in st.session_state.last_three_activities:
            st.write(act)
    else:
        st.caption("Keine Aktivitäten geladen.")
        
    st.divider()
    if st.sidebar.button("⚠️ Lokale Daten löschen", key="btn_clear_device_data"):
        cookie_manager.delete("auth_paket", key="cookie_del_auth")
        cookie_manager.delete("physio_paket", key="cookie_del_physio")
        
        for f_name in [get_plan_filename(), get_woche_filename(), get_status_filename()]:
            if os.path.exists(f_name):
                try: os.remove(f_name)
                except: pass
                
        for key in ["messages", "strava_context", "daten_geladen", "doc_names", "doc_texts", "doc_images", "temp_auth_data", "pending_auth", "auto_config_json", "trainingsplan", "wochenplan", "leistungsstatus", "last_three_activities", "upload_knowledge_files"]:
            if key in st.session_state: del st.session_state[key]
        time.sleep(0.5)
        st.rerun()

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
                    else: st.error("Das eingegebene Passwort ist falsch.")
                except Exception as e: st.error(f"Datei fehlerhaft: {e}")
    with tab2:
        in_pw = st.text_input("🔑 Wähle dein Master-Passwort", type="password", key="setup_pw")
        in_gemini = st.text_input("1. Gemini API Key", type="password", key="setup_gemini")
        in_client_id = st.text_input("2. Strava Client-ID", key="setup_id")
        in_client_secret = st.text_input("3. Geheimer Clientschlüssel", type="password", key="setup_secret")
        if in_client_id:
            auth_url = f"https://www.strava.com/oauth/authorize?client_id={in_client_id}&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=activity:read_all"
            st.markdown(f"[👉 Klicke hier, um Strava freizugeben]({auth_url})")
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
            else: st.error("Bitte fülle alle Felder aus!")
        if "auto_config_json" in st.session_state:
            st.download_button("📥 JETZT DEINE CONFIG.JSON HERUNTERLADEN", data=st.session_state["auto_config_json"], file_name="config.json", mime="application/json")
            if st.button("🔄 App starten", key="btn_start_after_setup"):
                if "pending_auth" in st.session_state: st.session_state.temp_auth_data = st.session_state.pending_auth
                st.rerun()

# --- HAUPT-APP BEREICH ---
else:
    client = genai.Client(api_key=gemini_key)

    if "temp_auth_data" in st.session_state:
        cookie_manager.set("auth_paket", json.dumps(st.session_state.temp_auth_data), key="cookie_set_main_auth")

    with st.expander("🧠 Trainer-Instruktionen"):
        new_instructions = st.text_area("Anweisungen", value=trainer_instructions, height=150, key="input_instructions")
        if st.button("💾 Speichern", key="btn_save_instructions"):
            physio_data["instructions"] = new_instructions
            cookie_manager.set("physio_paket", json.dumps(physio_data), key="cookie_set_instructions")
            st.success("Gespeichert!")

    with st.expander("📊 Physiologische Werte"):
        col_v, col_l, col_b = st.columns(3)
        with col_v: new_vo2max = st.text_input("VO2max Basis", value=vo2max, key="input_vo2max")
        with col_l: new_laktat = st.text_input("Laktatschwelle", value=laktatschwelle, key="input_laktat")
        with col_b: new_belastung = st.text_input("Fokus-Belastung", value=belastung, key="input_belastung")
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

    # --- ANZEIGE DER PLÄNE ---
    with st.expander("📅 Aktueller Wochenplan", expanded=bool(st.session_state.get("wochenplan"))):
        if st.session_state.get("wochenplan"):
            st.markdown(st.session_state.wochenplan)
            st.divider()
            st.download_button("📥 Wochenplan speichern (.md)", data=st.session_state.wochenplan, file_name="wochenplan.md", mime="text/markdown", key="dl_wp")
        else:
            st.info("Kein Wochenplan vorhanden. Hole deine Strava-Daten und klicke auf 'Wochenplan & Status aktualisieren'!")

    with st.expander("🏆 Langfristiger Masterplan", expanded=False):
        if st.session_state.get("trainingsplan"):
            st.markdown(st.session_state.trainingsplan)
            st.divider()
            col_md, col_txt = st.columns(2)
            with col_md: st.download_button("📥 Masterplan (.md)", data=st.session_state.trainingsplan, file_name="trainingsplan.md", mime="text/markdown", key="dl_mp_md")
            with col_txt: st.download_button("📥 Masterplan (.txt)", data=st.session_state.trainingsplan, file_name="trainingsplan.txt", mime="text/plain", key="dl_mp_txt")
        else:
            st.info("Kein langfristiger Masterplan vorhanden. Generiere zuerst deinen großen Masterplan.")

    st.divider()
    
    # --- SCHRITT 1: STRAVA-DATEN HOLEN ---
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
                            last_three = []
                            for act in activities:
                                t = act.get('sport_type', act.get('type', 'Unbekannt'))
                                d = act.get('distance', 0) / 1000
                                s = act.get('average_speed', 0)
                                date = act.get('start_date_local', '')[:10]
                                p = act.get('average_heartrate', 'Kein Puls')
                                
                                t_de = "Lauf" if t in ["Run", "Lauf"] else ("Radfahren" if t in ["Ride", "Cycling"] else t)
                                info = f"Pace: {(1000/s)/60:.2f} min/km" if t in ["Run", "Lauf"] and s > 0 else f"Geschw.: {s*3.6:.2f} km/h"
                                data += f"- [{date}] [{t}] {act.get('name')}: {d:.2f} km | {info} | Ø Puls: {p}\n"
                                
                                if len(last_three) < 3:
                                    try:
                                        dt = datetime.strptime(date, "%Y-%m-%d")
                                        date_str = dt.strftime("%d.%m.%y")
                                    except: date_str = date
                                    last_three.append(f"• {date_str} - {t_de} {d:.1f} km")
                                    
                            st.session_state.strava_context = data
                            st.session_state.last_three_activities = last_three
                            st.session_state.daten_geladen = True
                            
                            if "leistungsstatus" in st.session_state:
                                st.session_state.leistungsstatus["letzte_aktivitaeten"] = last_three
                                with open(get_status_filename(), "w", encoding="utf-8") as f:
                                    json.dump(st.session_state.leistungsstatus, f, ensure_ascii=False, indent=2)
                                    
                            st.success("Daten erfolgreich geladen! Letzte Aktivitäten in der Sidebar aktualisiert.")
                            st.rerun()
                        else: st.warning("Keine Aktivitäten gefunden.")
                    else: st.error(f"Fehler bei Strava. Code: {response.status_code}")
                except Exception as e: st.error(f"Verbindungsfehler: {e}")

    # --- SCHRITT 2: STEUERUNG DER PLÄNE (2-KNOPF-SYSTEM) ---
    if st.session_state.get("daten_geladen"):
        st.subheader("🗓️ 2. Trainingspläne & Status steuern")
        
        if not st.session_state.get("trainingsplan"):
            if st.button("✨ Großen Masterplan initial erstellen", key="btn_new_plan"):
                with st.spinner("Erstelle langfristigen Masterplan..."):
                    prompt = f"Erstelle einen neuen langfristigen Masterplan bis zum Marathon am 05.07.2026.\nHistorie:\n{st.session_state.strava_context}\nInstruktionen: {trainer_instructions}\n"
                    try:
                        resp = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt] + st.session_state.doc_images)
                        if resp.text:
                            st.session_state.trainingsplan = resp.text
                            with open(get_plan_filename(), "w", encoding="utf-8") as f:
                                f.write(resp.text)
                            st.success("Masterplan erfolgreich auf dem Server gesichert!")
                            st.rerun()
                    except Exception as e: st.error(f"Fehler: {e}")
        else:
            c_wp, c_mp = st.columns(2)
            with c_wp:
                if st.button("📅 Wochenplan & Status aktualisieren", key="btn_update_woche"):
                    with st.spinner("Berechne adaptiven Wochenplan & Leistungsstatus..."):
                        prompt = f"""
                        Du bist der persönliche KI-Laufcoach des Athleten.
                        Hier ist der aktuelle langfristige Masterplan:
                        {st.session_state.trainingsplan}
                        
                        Hier sind die neuesten Strava-Trainingsdaten:
                        {st.session_state.strava_context}
                        
                        Instruktionen (z.B. Tapering-Ziele):
                        {trainer_instructions}
                        
                        Physiologische Werte: VO2max: {vo2max}, Laktat: {laktatschwelle}, Belastung: {belastung}
                        
                        AUFGABE:
                        1. Erstelle einen adaptiven Wochenplan für den Rest DIESER aktuellen Woche. Passe ihn intelligent an, falls zusätzliche Aktivitäten (Radtouren) erfolgten oder Einheiten verändert wurden.
                        2. Berechne den Leistungszustand: Schätze den VO2max (Zahl), gib präzise Laufprognosen für 5 km, 10 km, 21 km und bewerte die akute Belastung.
                        
                        ANTWORT-FORMAT (STRENG EINHALTEN):
                        ===STATUS_START===
                        {{
                          "vo2max": "Zahl (z.B. 51.2)",
                          "prognose_5k": "Zeit (z.B. 21:40 min)",
                          "prognose_10k": "Zeit (z.B. 45:15 min)",
                          "prognose_21k": "Zeit (z.B. 1:40:30 std)",
                          "belastung": "Kurzer Statustext"
                        }}
                        ===STATUS_END===
                        
                        ===WOCHENPLAN_START===
                        ### 📅 Dein adaptiver Wochenplan (Restwoche)
                        *Hier folgt der strukturierte Wochenplan im Markdown-Format...*
                        ===WOCHENPLAN_END===
                        """
                        try:
                            resp = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt] + st.session_state.doc_images)
                            text = resp.text
                            if "===STATUS_START===" in text and "===WOCHENPLAN_START===" in text:
                                status_part = text.split("===STATUS_START===")[1].split("===STATUS_END===")[0].strip()
                                woche_part = text.split("===WOCHENPLAN_START===")[1].split("===WOCHENPLAN_END===")[0].strip()
                                
                                try:
                                    s_json = json.loads(status_part)
                                    s_json["letzte_aktivitaeten"] = st.session_state.get("last_three_activities", [])
                                    s_json["letztes_update"] = datetime.now().strftime("%d.%m.%Y")
                                    with open(get_status_filename(), "w", encoding="utf-8") as f:
                                        json.dump(s_json, f, ensure_ascii=False, indent=2)
                                    st.session_state.leistungsstatus = s_json
                                except Exception as json_err:
                                    st.error(f"Status-Parsing-Fehler: {json_err}")
                                    
                                st.session_state.wochenplan = woche_part
                                with open(get_woche_filename(), "w", encoding="utf-8") as f:
                                    f.write(woche_part)
                                st.success("Wochenplan & Leistungsstatus erfolgreich aktualisiert!")
                                st.rerun()
                            else: st.error("Fehler im KI-Antwortformat. Bitte erneut versuchen.")
                        except Exception as e: st.error(f"Fehler bei Verbindung: {e}")
            
            with c_mp:
                if st.button("🏆 Masterplan aktualisieren", key="btn_update_master"):
                    with st.spinner("Aktualisiere großen Masterplan..."):
                        prompt = f"Hier ist mein alter Masterplan:\n{st.session_state.trainingsplan}\n\nHier sind neue Trainingsdaten:\n{st.session_state.strava_context}\n\nInstruktionen:\n{trainer_instructions}\n\nSchreibe den großen Masterplan intelligent bis zum 05.07.2026 neu."
                        try:
                            resp = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt] + st.session_state.doc_images)
                            if resp.text:
                                st.session_state.trainingsplan = resp.text
                                with open(get_plan_filename(), "w", encoding="utf-8") as f:
                                    f.write(resp.text)
                                st.success("Langfristiger Masterplan erfolgreich aktualisiert!")
                                st.rerun()
                        except Exception as e: st.error(f"Fehler: {e}")

    # --- COACH SCHNELL-CHECK ---
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
                except Exception as e: st.error(f"Fehler: {e}")
                    
        if c2.button("📅 Wochenplan Zusammenfassung", key="btn_check_week"):
            with st.spinner("Analysiere Woche..."):
                req = [f"Gib mir eine kompakte Zusammenfassung des Trainings für die nächsten 7 Tage basierend auf:\n{st.session_state.trainingsplan}"] + st.session_state.doc_images
                try:
                    resp = client.models.generate_content(model='gemini-2.5-flash', contents=req)
                    if resp.text: st.write(resp.text)
                except Exception as e: st.error(f"Fehler: {e}")

    st.divider()
    st.subheader("💬 Chat mit Coach")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if user_input := st.chat_input("Nachricht an den Coach...", key="input_chat"):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"): st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Tippt..."):
                prompt = f"Du bist Coach. Plan:\n{st.session_state.get('wochenplan', st.session_state.get('trainingsplan'))}\nDaten:\n{st.session_state.strava_context}\nFrage: {user_input}"
                req = [prompt] + st.session_state.doc_images
                try:
                    resp = client.models.generate_content(model='gemini-2.5-flash', contents=req)
                    if resp.text:
                        st.markdown(resp.text)
                        st.session_state.messages.append({"role": "assistant", "content": resp.text})
                except Exception as e: st.error(f"Fehler: {e}")
