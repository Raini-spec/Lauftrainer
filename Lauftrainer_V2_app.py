# ==============================================================================
# 📦 BIBLIOTHEKEN LADEN (IMPORT-BEREICH)
# ==============================================================================
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

# --- INITIALISIERUNG DER SEITE ---
st.set_page_config(page_title="KI Trainer", layout="centered")

# --- COOKIE MANAGER STARTEN ---
cookie_manager = stx.CookieManager()
st.write("") 

# --- TITELZEILEN ---
st.title("🏃‍♂️🚴 KI Trainer: Strava & Gemini")
st.caption("🔒 **Version 4.80** – Bugfix (Ampel) & All-in-One Masterplan-Updates")

# ==============================================================================
# 🧠 REKURSIVES GEDÄCHTNIS (STREAMLIT SESSION STATE)
# ==============================================================================
if "messages" not in st.session_state: st.session_state.messages = []
if "strava_context" not in st.session_state: st.session_state.strava_context = ""
if "doc_names" not in st.session_state: st.session_state.doc_names = []
if "doc_texts" not in st.session_state: st.session_state.doc_texts = []
if "doc_images" not in st.session_state: st.session_state.doc_images = []
if "ansicht" not in st.session_state: st.session_state.ansicht = "📅 Mein Trainings-Dashboard"

# ==============================================================================
# 🍪 LANGZEITGEDÄCHTNIS (COOKIE-LOGIK)
# ==============================================================================
auth_cookie = cookie_manager.get("auth_paket")
auth_data = {}
if auth_cookie:
    try: auth_data = json.loads(auth_cookie) if isinstance(auth_cookie, str) else auth_cookie
    except: pass
if "temp_auth_data" in st.session_state: auth_data = st.session_state.temp_auth_data

physio_cookie = cookie_manager.get("physio_paket")
physio_data = {}
if physio_cookie:
    try: physio_data = json.loads(physio_cookie) if isinstance(physio_cookie, str) else physio_cookie
    except: pass

# --- AUTOMATISCHES WIEDERHERSTELLEN AUS DEM BROWSER-SAFE ---
app_backup_cookie = cookie_manager.get("app_backup_paket")
if app_backup_cookie:
    try: 
        backup_data = json.loads(app_backup_cookie) if isinstance(app_backup_cookie, str) else app_backup_cookie
        if backup_data:
            if "trainingsplan" not in st.session_state and backup_data.get("trainingsplan"):
                st.session_state.trainingsplan = backup_data["trainingsplan"]
            if "wochenplan" not in st.session_state and backup_data.get("wochenplan"):
                st.session_state.wochenplan = backup_data["wochenplan"]
            if "leistungsstatus" not in st.session_state and backup_data.get("leistungsstatus"):
                st.session_state.leistungsstatus = backup_data["leistungsstatus"]
            if "heute_training" not in st.session_state and backup_data.get("heute_training"):
                st.session_state.heute_training = backup_data["heute_training"]
    except: pass

# ==============================================================================
# ⚙️ HILFSFUNKTIONEN (WERKZEUGBOX)
# ==============================================================================
def save_all_to_state_and_cookies(plan_text=None, woche_text=None, status_json=None, heute_text=None):
    if plan_text is not None: st.session_state.trainingsplan = plan_text
    if woche_text is not None: st.session_state.wochenplan = woche_text
    if status_json is not None: st.session_state.leistungsstatus = status_json
    if heute_text is not None: st.session_state.heute_training = heute_text
    
    backup_paket = {
        "trainingsplan": st.session_state.get("trainingsplan", ""),
        "wochenplan": st.session_state.get("wochenplan", ""),
        "leistungsstatus": st.session_state.get("leistungsstatus", {}),
        "heute_training": st.session_state.get("heute_training", "")
    }
    cookie_manager.set("app_backup_paket", json.dumps(backup_paket), key=f"set_backup_{int(time.time())}")

def get_valid_strava_token():
    global auth_data
    expires_at = auth_data.get("expires_at")
    if not expires_at or time.time() > (float(expires_at) - 300):
        with st.spinner("Erneuere Strava-Zugriff..."):
            url = "https://www.strava.com/oauth/token"
            payload = {
                "client_id": auth_data.get("client_id"),
                "client_secret": auth_data.get("client_secret"),
                "refresh_token": auth_data.get("refresh_token"),
                "grant_type": "refresh_token"
            }
            res = requests.post(url, data=payload)
            if res.status_code == 200:
                data = res.json()
                auth_data["access_token"] = data["access_token"]
                auth_data["refresh_token"] = data["refresh_token"]
                auth_data["expires_at"] = data["expires_at"]
                cookie_manager.set("auth_paket", json.dumps(auth_data), key="cookie_set_refresh")
                return data["access_token"]
            return None
    return auth_data.get("access_token")

def load_and_format_strava_data():
    strava_token = get_valid_strava_token()
    if not strava_token: return False
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
                if "leistungsstatus" in st.session_state:
                    st.session_state.leistungsstatus["letzte_aktivitaeten"] = last_three
                return True
            return False
        return False
    except: return False

# ==============================================================================
# 🎛️ COCKPIT LINKS (STREAMLIT SIDEBAR)
# ==============================================================================
with st.sidebar:
    st.header("🧭 Navigation")
    if st.button("📅 Trainings-Dashboard", use_container_width=True): st.session_state.ansicht = "📅 Mein Trainings-Dashboard"
    if st.button("🧠 Trainer-Instruktionen", use_container_width=True): st.session_state.ansicht = "🧠 Trainer-Instruktionen"
    if st.button("📊 Physiologische Werte", use_container_width=True): st.session_state.ansicht = "📊 Physiologische Werte"
    if st.button("📄 Hintergrundwissen", use_container_width=True): st.session_state.ansicht = "📄 Hintergrundwissen (Dateien)"
    if st.button("💾 Daten-Backup Center", use_container_width=True): st.session_state.ansicht = "💾 Daten-Backup Center"

    st.divider()

    st.header("📊 Leistungszustand")
    if "leistungsstatus" in st.session_state and st.session_state.leistungsstatus:
        status = st.session_state.leistungsstatus
        st.caption(f"Letztes Update: {status.get('letztes_update', '---')}")
        st.metric("Geschätzter VO2max", f"⚡ {status.get('vo2max', '---')}")
        
        st.markdown("**🎯 Laufprognosen:**")
        st.markdown(f"• **5 km:** {status.get('prognose_5k', '---')}")
        st.markdown(f"• **10 km:** {status.get('prognose_10k', '---')}")
        st.markdown(f"• **21 km:** {status.get('prognose_21k', '---')}")
        
        st.write("")
        st.markdown("**🔥 Akute Belastung:**")
        belastung_text = status.get('belastung', 'Niedrig')
        
        # BUGFIX: Sicheres Auslesen des Prozentwerts (verhindert Abstürze, falls KI "20%" ausgibt)
        raw_b = status.get("belastung_prozent", 20)
        try:
            if isinstance(raw_b, str): raw_b = raw_b.replace("%", "").strip()
            belastung_prozent = int(float(raw_b))
        except:
            belastung_prozent = 20
        
        if belastung_prozent < 45: color_code = "#2ecc71"  # Grün
        elif belastung_prozent < 75: color_code = "#f1c40f"  # Gelb
        else: color_code = "#e74c3c"  # Rot
        
        # BUGFIX: unsafe_allow_html=True statt unsafe_html
        st.markdown(f"""
            <div style="width: 100%; background-color: #f0f2f6; border-radius: 4px; height: 8px; margin-bottom: 4px;">
                <div style="width: {belastung_prozent}%; background-color: {color_code}; height: 8px; border-radius: 4px;"></div>
            </div>
            <span style="font-size: 0.85rem; color: #555;">Status: <i>{belastung_text} ({belastung_prozent}%)</i></span>
        """, unsafe_allow_html=True)
    else:
        st.info("Kein aktiver Leistungsstatus im Speicher.")
        
    st.divider()
    st.header("👟 Letzte Aktivitäten")
    if "leistungsstatus" in st.session_state and st.session_state.leistungsstatus and st.session_state.leistungsstatus.get("letzte_aktivitaeten"):
        for act in st.session_state.leistungsstatus.get("letzte_aktivitaeten"): st.write(act)
    elif "last_three_activities" in st.session_state:
        for act in st.session_state.last_three_activities: st.write(act)

    st.divider()
    if st.button("⚠️ Lokale Daten löschen", use_container_width=True, type="primary"):
        cookie_manager.delete("auth_paket")
        cookie_manager.delete("physio_paket")
        cookie_manager.delete("app_backup_paket")
        for key in ["messages", "strava_context", "doc_names", "doc_texts", "doc_images", "temp_auth_data", "trainingsplan", "wochenplan", "leistungsstatus", "last_three_activities", "heute_training", "ansicht"]:
            if key in st.session_state: del st.session_state[key]
        time.sleep(0.5)
        st.rerun()

# ==============================================================================
# 🔑 SCHLEUSE (LOGIN ODER HAUPT-APP)
# ==============================================================================
gemini_key = auth_data.get("gemini_key")
access_token = auth_data.get("access_token")
trainer_instructions = physio_data.get("instructions", "")
vo2max = physio_data.get("vo2max", "")
laktatschwelle = physio_data.get("laktat", "")
belastung = physio_data.get("belastung", "")

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
                    st.session_state["auto_config_json"] = json.dumps(neues_paket, indent=2)
                    st.success("App konfiguriert!")
                    
        if "auto_config_json" in st.session_state:
            st.download_button("📥 JETZT CONFIG.JSON HERUNTERLADEN", data=st.session_state["auto_config_json"], file_name="config.json", mime="application/json")
            if st.button("🔄 App starten", key="btn_start_after_setup"):
                if "auto_config_json" in st.session_state: st.session_state.temp_auth_data = json.loads(st.session_state["auto_config_json"])
                st.rerun()

# ==============================================================================
# 🏃‍♂️ HAUPT-APP BEREICH (DYNAMISCH GESTEUERT DURCH NAVI LINKS)
# ==============================================================================
else:
    client = genai.Client(api_key=gemini_key)
    if "temp_auth_data" in st.session_state:
        cookie_manager.set("auth_paket", json.dumps(st.session_state.temp_auth_data), key="cookie_set_main_auth")

    # --- DATEN-DASHBOARD ANZEIGEN (STANDARD-ANSICHT) ---
    if st.session_state.ansicht == "📅 Mein Trainings-Dashboard":
        if st.session_state.get("heute_training"):
            st.info(f"🎯 **HEUTE AUF DEM PLAN:**\n\n{st.session_state.heute_training}")
            st.write("")

        st.subheader("📅 Aktueller Wochenplan")
        if st.session_state.get("wochenplan"):
            st.markdown(st.session_state.wochenplan)
            st.download_button("📥 Wochenplan speichern (.md)", data=st.session_state.wochenplan, file_name="wochenplan.md", mime="text/markdown", key="dl_wp")
        else:
            st.info("Kein Wochenplan vorhanden. Klicke unten auf 'Wochenplan & Status aktualisieren'!")

        st.write("")
        st.subheader("🏆 Langfristiger Masterplan")
        if st.session_state.get("trainingsplan"):
            with st.expander("Vollständigen Masterplan einsehen", expanded=False):
                st.markdown(st.session_state.trainingsplan)
                st.download_button("📥 Masterplan (.md)", data=st.session_state.trainingsplan, file_name="trainingsplan.md", mime="text/markdown", key="dl_mp_md")
        else:
            st.info("Kein langfristiger Masterplan vorhanden. Generiere zuerst deinen großen Masterplan.")

    # --- TRAINER-INSTRUCTION MENÜ ---
    elif st.session_state.ansicht == "🧠 Trainer-Instruktionen":
        st.subheader("🧠 Trainer-Instruktionen")
        new_instructions = st.text_area("Anweisungen für die KI (Ziele, Fokus, Einschränkungen)", value=trainer_instructions, height=300, key="input_instructions")
        if st.button("💾 Speichern", key="btn_save_instructions"):
            physio_data["instructions"] = new_instructions
            cookie_manager.set("physio_paket", json.dumps(physio_data), key="cookie_set_instructions")
            st.success("Gespeichert!")

    # --- PHYSIO MENÜ ---
    elif st.session_state.ansicht == "📊 Physiologische Werte":
        st.subheader("📊 Physiologische Werte")
        col_v, col_l, col_b = st.columns(3)
        with col_v: new_vo2max = st.text_input("VO2max Basis", value=vo2max, key="input_vo2max")
        with col_l: new_laktat = st.text_input("Laktatschwelle", value=laktatschwelle, key="input_laktat")
        with col_b: new_belastung = st.text_input("Fokus-Belastung", value=belastung, key="input_belastung")
        if st.button("💾 Werte speichern", key="btn_save_physio"):
            physio_data.update({"vo2max": new_vo2max, "laktat": new_laktat, "belastung": new_belastung})
            cookie_manager.set("physio_paket", json.dumps(physio_data), key="cookie_set_physio_values")
            st.success("Gespeichert!")

    # --- DATEI MANAGER ---
    elif st.session_state.ansicht == "📄 Hintergrundwissen (Dateien)":
        st.subheader("📄 Hintergrundwissen (Dateien) verwalten")
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

    # --- DATA-BACKUP MENÜ ---
    elif st.session_state.ansicht == "💾 Daten-Backup Center":
        st.subheader("💾 Daten-Backup Center")
        st.caption("Falls der Server deine Pläne gelöscht hat, kannst du hier dein Backup einspielen oder den aktuellen Stand sichern.")
        c_exp, c_imp = st.columns(2)
        with c_exp:
            current_backup = {
                "trainingsplan": st.session_state.get("trainingsplan", ""),
                "wochenplan": st.session_state.get("wochenplan", ""),
                "leistungsstatus": st.session_state.get("leistungsstatus", {}),
                "heute_training": st.session_state.get("heute_training", "")
            }
            st.download_button("📥 Backup-Datei herunterladen", data=json.dumps(current_backup, indent=2, ensure_ascii=False), file_name="trainer_backup.json", mime="application/json", key="main_btn_export")
        with c_imp:
            uploaded_backup = st.file_uploader("📤 Backup-Datei hochladen", type=["json"], key="main_upload_backup_file")
            if st.button("🔄 Daten aus Datei wiederherstellen", key="btn_trigger_import"):
                if uploaded_backup:
                    try:
                        b_content = json.load(uploaded_backup)
                        save_all_to_state_and_cookies(
                            plan_text=b_content.get("trainingsplan", ""), 
                            woche_text=b_content.get("wochenplan", ""), 
                            status_json=b_content.get("leistungsstatus", {}),
                            heute_text=b_content.get("heute_training", "")
                        )
                        st.success("Backup erfolgreich geladen!")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e: st.error(f"Fehler beim Laden: {e}")

    # ==============================================================================
    # 💥 DIE KI-STEUERZENTRALE (ALWAYS VISIBLE AM UNTEREN ENDE)
    # ==============================================================================
    st.divider()
    st.subheader("🗓️ Trainingspläne & Status steuern")
    
    heute_iso = datetime.now().strftime("%A, %d. %B %Y")
    
    zeit_befehl = f"""
    ⚠️ WICHTIGER SYSTEM-ZEITANKER:
    Heute ist exakt der {heute_iso}. Wir befinden uns im Jahr 2026!
    Jedes Strava-Training mit einem Datum aus 2026 ist brandaktuell.
    Rechne alle Pläne penibel von diesem heutigen Datum ({heute_iso}) in die Zukunft. 
    Behandle das aktuelle Jahr NIEMALS als 2024 oder ein anderes Jahr.
    Berücksichtige als Wettkampfdatum ausschließlich das Datum, das in den Instruktionen steht!
    """

    # --- ZENTRALES FORMAT FÜR ALLE UPDATES ---
    output_format_alle = """
    ANTWORT-FORMAT (STRENG EINHALTEN):
    ===STATUS_START===
    {
      "vo2max": "Zahl (z.B. 51.2)",
      "prognose_5k": "Zeit (z.B. 21:40 min)",
      "prognose_10k": "Zeit (z.B. 45:15 min)",
      "prognose_21k": "Zeit (z.B. 1:40:30 std)",
      "belastung": "Kurzer Statustext (z.B. Niedrig)",
      "belastung_prozent": "Zahl zwischen 0 und 100 (ohne %-Zeichen, z.B. 25)"
    }
    ===STATUS_END===
    
    ===HEUTE_START===
    Hier steht nur die heutige Einheit in 1-2 prägnanten Sätzen.
    ===HEUTE_END===
    
    ===WOCHENPLAN_START===
    ### 📅 Dein adaptiver Wochenplan (Restwoche)
    *Hier folgt der strukturierte Wochenplan im Markdown-Format...*
    ===WOCHENPLAN_END===
    """

    if not st.session_state.get("trainingsplan"):
        if st.button("✨ Großen Masterplan initial erstellen", key="btn_new_plan"):
            with st.spinner("Lade aktuelle Strava-Daten und erstelle alle Pläne..."):
                if load_and_format_strava_data():
                    prompt = f"""
                    {zeit_befehl}
                    Erstelle einen neuen langfristigen Masterplan.
                    Historie: {st.session_state.strava_context}
                    Instruktionen: {trainer_instructions}
                    
                    AUFGABE:
                    1. Erstelle den großen Masterplan.
                    2. Erstelle passend dazu den Wochenplan für den Rest DIESER Woche.
                    3. Extrahiere die heutige Einheit.
                    4. Berechne den Leistungszustand.
                    
                    {output_format_alle}
                    
                    ===MASTERPLAN_START===
                    ### 🏆 Dein Langfristiger Masterplan
                    *Hier folgt der große Masterplan...*
                    ===MASTERPLAN_END===
                    """
                    try:
                        resp = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt] + st.session_state.doc_images)
                        text = resp.text
                        
                        master_part = text.split("===MASTERPLAN_START===")[1].split("===MASTERPLAN_END===")[0].strip() if "===MASTERPLAN_START===" in text else text
                        woche_part = text.split("===WOCHENPLAN_START===")[1].split("===WOCHENPLAN_END===")[0].strip() if "===WOCHENPLAN_START===" in text else ""
                        heute_part = text.split("===HEUTE_START===")[1].split("===HEUTE_END===")[0].strip() if "===HEUTE_START===" in text else ""
                        status_part = text.split("===STATUS_START===")[1].split("===STATUS_END===")[0].strip() if "===STATUS_START===" in text else "{}"
                        
                        s_json = {}
                        try:
                            s_json = json.loads(status_part)
                            s_json["letzte_aktivitaeten"] = st.session_state.get("last_three_activities", [])
                            s_json["letztes_update"] = datetime.now().strftime("%d.%m.%Y")
                        except: pass
                        
                        save_all_to_state_and_cookies(plan_text=master_part, woche_text=woche_part, status_json=s_json, heute_text=heute_part)
                        st.success("Masterplan & Wochenplan erfolgreich erstellt!")
                        st.rerun()
                    except Exception as e: st.error(f"Fehler: {e}")
    else:
        c_wp, c_mp = st.columns(2)
        with c_wp:
            if st.button("📅 Wochenplan & Status aktualisieren", key="btn_update_woche"):
                with st.spinner("Hole Strava-Daten und berechne adaptiven Wochenplan..."):
                    if load_and_format_strava_data():
                        prompt = f"""
                        {zeit_befehl}
                        Hier ist der aktuelle Masterplan:\n{st.session_state.trainingsplan}
                        Hier sind die neuesten Strava-Daten:\n{st.session_state.strava_context}
                        Instruktionen:\n{trainer_instructions}
                        
                        AUFGABE:
                        1. Erstelle einen adaptiven Wochenplan für den Rest DIESER aktuellen Woche (basierend auf {heute_iso}).
                        2. Extrahiere NUR die heutige Trainingseinheit.
                        3. Berechne den Leistungszustand.
                        
                        {output_format_alle}
                        """
                        try:
                            resp = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt] + st.session_state.doc_images)
                            text = resp.text
                            if "===STATUS_START===" in text and "===WOCHENPLAN_START===" in text and "===HEUTE_START===" in text:
                                status_part = text.split("===STATUS_START===")[1].split("===STATUS_END===")[0].strip()
                                heute_part = text.split("===HEUTE_START===")[1].split("===HEUTE_END===")[0].strip()
                                woche_part = text.split("===WOCHENPLAN_START===")[1].split("===WOCHENPLAN_END===")[0].strip()
                                
                                s_json = {}
                                try:
                                    s_json = json.loads(status_part)
                                    s_json["letzte_aktivitaeten"] = st.session_state.get("last_three_activities", [])
                                    s_json["letztes_update"] = datetime.now().strftime("%d.%m.%Y")
                                except: pass
                                    
                                save_all_to_state_and_cookies(woche_text=woche_part, status_json=s_json, heute_text=heute_part)
                                st.success("Wochenplan & Heute-Widget erfolgreich aktualisiert!")
                                st.rerun()
                        except Exception as e: st.error(f"Fehler: {e}")
        
        with c_mp:
            if st.button("🏆 Masterplan aktualisieren", key="btn_update_master"):
                with st.spinner("Hole Strava-Daten und aktualisiere alle Pläne..."):
                    if load_and_format_strava_data():
                        prompt = f"""
                        {zeit_befehl}
                        Hier ist mein alter Masterplan:\n{st.session_state.trainingsplan}
                        Hier sind neue Trainingsdaten:\n{st.session_state.strava_context}
                        Instruktionen:\n{trainer_instructions}
                        
                        AUFGABE:
                        1. Schreibe den großen Masterplan intelligent neu.
                        2. Erstelle passend dazu den adaptiven Wochenplan für den Rest DIESER Woche.
                        3. Extrahiere die heutige Einheit.
                        4. Berechne den Leistungszustand.
                        
                        {output_format_alle}
                        
                        ===MASTERPLAN_START===
                        ### 🏆 Dein Langfristiger Masterplan
                        *Hier folgt der große Masterplan...*
                        ===MASTERPLAN_END===
                        """
                        try:
                            resp = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt] + st.session_state.doc_images)
                            text = resp.text
                            
                            master_part = text.split("===MASTERPLAN_START===")[1].split("===MASTERPLAN_END===")[0].strip() if "===MASTERPLAN_START===" in text else st.session_state.get("trainingsplan", "")
                            woche_part = text.split("===WOCHENPLAN_START===")[1].split("===WOCHENPLAN_END===")[0].strip() if "===WOCHENPLAN_START===" in text else st.session_state.get("wochenplan", "")
                            heute_part = text.split("===HEUTE_START===")[1].split("===HEUTE_END===")[0].strip() if "===HEUTE_START===" in text else st.session_state.get("heute_training", "")
                            status_part = text.split("===STATUS_START===")[1].split("===STATUS_END===")[0].strip() if "===STATUS_START===" in text else "{}"
                            
                            s_json = {}
                            try:
                                s_json = json.loads(status_part)
                                s_json["letzte_aktivitaeten"] = st.session_state.get("last_three_activities", [])
                                s_json["letztes_update"] = datetime.now().strftime("%d.%m.%Y")
                            except: pass
                            
                            save_all_to_state_and_cookies(plan_text=master_part, woche_text=woche_part, status_json=s_json, heute_text=heute_part)
                            st.success("Masterplan, Wochenplan & Status erfolgreich aktualisiert!")
                            st.rerun()
                        except Exception as e: st.error(f"Fehler: {e}")

# ==============================================================================
# 💬 CHAT-INTERFAZ (COACH TALK)
# ==============================================================================
    st.divider()
    st.subheader("💬 Chat mit Coach")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if user_input := st.chat_input("Nachricht an den Coach..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"): st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Tippt..."):
                prompt = f"{zeit_befehl}\n\nDu bist Coach. Plan:\n{st.session_state.get('wochenplan', st.session_state.get('trainingsplan'))}\nDaten:\n{st.session_state.strava_context}\nFrage: {user_input}"
                try:
                    resp = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt] + st.session_state.doc_images)
                    if resp.text:
                        st.markdown(resp.text)
                        st.session_state.messages.append({"role": "assistant", "content": resp.text})
                except Exception as e: st.error(f"Fehler: {e}")
