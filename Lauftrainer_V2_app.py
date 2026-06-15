# ==============================================================================
# 📦 BIBLIOTHEKEN LADEN (IMPORT-BEREICH)
# ==============================================================================
# Hier holen wir uns die Werkzeuge, die Python standardmäßig nicht mitbringt.
import streamlit as st  # Das Framework für unsere gesamte Benutzeroberfläche (UI)
import requests  # Ermöglicht das Senden von HTTP-Anfragen (wichtig für die Strava-API)
from google import genai  # Das offizielle Google SDK, um mit der Gemini-KI zu sprechen
import time  # Für Zeitverzögerungen und Zeitstempel-Berechnungen
from datetime import datetime  # Um das aktuelle Datum und Uhrzeiten zu verarbeiten
import PyPDF2  # Werkzeug, um hochgeladene PDF-Dateien auszulesen
import extra_streamlit_components as stx  # Spezial-Erweiterung für den Cookie-Manager
import json  # Erlaubt das Lesen und Schreiben von strukturierten Daten-Paketen
from PIL import Image  # Bildverarbeitung (wichtig für hochgeladene Trainings-Grafiken)
import os  # Betriebssystem-Schnittstelle (wurde für lokale Server-Dateien genutzt)

# --- INITIALISIERUNG DER SEITE ---
# st.set_page_config MUSS immer der allererste Streamlit-Befehl im Code sein!
st.set_page_config(page_title="KI Trainer", layout="centered")

# --- COOKIE MANAGER STARTEN ---
# Erstellt das Objekt, das auf die Festplatte des Nutzers zugreifen und Cookies lesen/schreiben kann.
cookie_manager = stx.CookieManager()
st.write("")  # Ein kleiner optischer Hack für einen sauberen Abstand ganz oben

# --- TITELZEILEN ---
st.title("🏃‍♂️🚴 KI Trainer: Strava & Gemini")
st.caption("🔒 **Version 4.31** – Zeitanker 2026 & Dokumentierter Quellcode")


# ==============================================================================
# 🧠 REKURSIVES GEDÄCHTNIS (STREAMLIT SESSION STATE)
# ==============================================================================
# Streamlit vergisst bei JEDEM Klick auf der Seite alle Variablen (Code läuft neu an).
# Der 'session_state' ist das Kurzzeitgedächtnis, das Daten während der Sitzung behält.
if "messages" not in st.session_state: st.session_state.messages = []  # Chat-Verlauf
if "strava_context" not in st.session_state: st.session_state.strava_context = ""  # Formatierte Strava-Daten
if "doc_names" not in st.session_state: st.session_state.doc_names = []  # Namen der Wissens-Dateien
if "doc_texts" not in st.session_state: st.session_state.doc_texts = []  # Inhalte der Text-Dateien
if "doc_images" not in st.session_state: st.session_state.doc_images = []  # Geladene Bilder


# ==============================================================================
# 🍪 LANGZEITGEDÄCHTNIS (COOKIE-LOGIK)
# ==============================================================================
# Wir holen uns die Daten, die permanent im Browser des Nutzers gespeichert sind.
auth_cookie = cookie_manager.get("auth_paket")
auth_data = {}
if auth_cookie:
    try: auth_data = json.loads(auth_cookie) if isinstance(auth_cookie, str) else auth_cookie
    except: pass
# Falls wir gerade im Setup-Prozess sind, überschreiben wir die Daten mit den temporären Werten
if "temp_auth_data" in st.session_state: auth_data = st.session_state.temp_auth_data

physio_cookie = cookie_manager.get("physio_paket")
physio_data = {}
if physio_cookie:
    try: physio_data = json.loads(physio_cookie) if isinstance(physio_cookie, str) else physio_cookie
    except: pass

# --- AUTOMATISCHES WIEDERHERSTELLEN AUS DEM BROWSER-SAFE ---
# Falls der Server abstürzt, holen wir die Pläne lautlos aus diesem Cookie zurück
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
    except: pass


# ==============================================================================
# ⚙️ HILFSFUNKTIONEN (WERKZEUGBOX)
# ==============================================================================

# --- ZENTRALE SPEICHER-FUNKTION ---
def save_all_to_state_and_cookies(plan_text=None, woche_text=None, status_json=None):
    """Speichert die Trainingspläne im Kurzzeitgedächtnis UND im permanenten Browser-Cookie."""
    if plan_text: st.session_state.trainingsplan = plan_text
    if woche_text: st.session_state.wochenplan = woche_text
    if status_json: st.session_state.leistungsstatus = status_json
    
    backup_paket = {
        "trainingsplan": st.session_state.get("trainingsplan", ""),
        "wochenplan": st.session_state.get("wochenplan", ""),
        "leistungsstatus": st.session_state.get("leistungsstatus", {})
    }
    # Wir hängen einen Zeitstempel an den Key an, damit der Browser merkt, dass sich Daten geändert haben
    cookie_manager.set("app_backup_paket", json.dumps(backup_paket), key=f"set_backup_{int(time.time())}")

# --- STRAVA TOKEN-TÜRSTEHER ---
def get_valid_strava_token():
    """Prüft, ob das Strava-Zugangstoken abgelaufen ist. Wenn ja, fordert es vollautomatisch ein neues an."""
    global auth_data
    expires_at = auth_data.get("expires_at")
    
    # Ein Strava-Token hält 6 Stunden. Wenn es in weniger als 5 Minuten (300 Sek) abläuft, erneuern wir es.
    if not expires_at or time.time() > (float(expires_at) - 300):
        with st.spinner("Erneuere Strava-Zugriff..."):
            url = "https://www.strava.com/oauth/token"
            payload = {
                "client_id": auth_data.get("client_id"),
                "client_secret": auth_data.get("client_secret"),
                "refresh_token": auth_data.get("refresh_token"),
                "grant_type": "refresh_token"
            }
            res = requests.post(url, data=payload) # Sende die Daten per POST-Befehl an Strava
            if res.status_code == 200:
                data = res.json()
                auth_data["access_token"] = data["access_token"]
                auth_data["refresh_token"] = data["refresh_token"]
                auth_data["expires_at"] = data["expires_at"]
                cookie_manager.set("auth_paket", json.dumps(auth_data), key="cookie_set_refresh")
                return data["access_token"]
            return None
    return auth_data.get("access_token")

# --- DATA-MINING: STRAVA IMPORT ---
def load_and_format_strava_data():
    """Hiebt die letzten 30 Aktivitäten aus der Strava-API und übersetzt sie in Text für die KI."""
    strava_token = get_valid_strava_token()
    if not strava_token: return False
    try:
        # GET-Anfrage an Strava. per_page=30 regelt die Anzahl der geladenen Einheiten
        response = requests.get(f"https://www.strava.com/api/v3/athlete/activities?per_page=30", headers={"Authorization": f"Bearer {strava_token}"})
        if response.status_code == 200:
            activities = response.json()
            if activities:
                data = ""
                last_three = []
                for act in activities:
                    t = act.get('sport_type', act.get('type', 'Unbekannt'))
                    d = act.get('distance', 0) / 1000  # Strava liefert Meter, wir rechnen in Kilometer um
                    s = act.get('average_speed', 0)  # Geschwindigkeit in m/s
                    date = act.get('start_date_local', '')[:10]  # Schneidet das Datum aus (YYYY-MM-DD)
                    p = act.get('average_heartrate', 'Kein Puls')
                    
                    t_de = "Lauf" if t in ["Run", "Lauf"] else ("Radfahren" if t in ["Ride", "Cycling"] else t)
                    # Berechnung der berüchtigten Läufer-Pace (Minuten pro Kilometer) aus m/s
                    info = f"Pace: {(1000/s)/60:.2f} min/km" if t in ["Run", "Lauf"] and s > 0 else f"Geschw.: {s*3.6:.2f} km/h"
                    data += f"- [{date}] [{t}] {act.get('name')}: {d:.2f} km | {info} | Ø Puls: {p}\n"
                    
                    # Extrahiere die Spitzen-3 für die Seitenleiste
                    if len(last_three) < 3:
                        try:
                            dt = datetime.strptime(date, "%Y-%m-%d")
                            date_str = dt.strftime("%d.%m.%y")
                        except: date_str = date
                        last_three.append(f"• {date_str} - {t_de} {d:.1f} km")
                        
                st.session_state.strava_context = data
                st.session_state.last_three_activities = last_three
                
                # Wenn ein Leistungsstatus existiert, weben wir die 3 Aktivitäten direkt dort ein
                if "leistungsstatus" in st.session_state:
                    st.session_state.leistungsstatus["letzte_aktivitaeten"] = last_three
                    save_all_to_state_and_cookies(status_json=st.session_state.leistungsstatus)
                return True
            return False
        return False
    except: return False


# ==============================================================================
# 🎛️ COCKPIT LINKS (STREMLIT SIDEBAR)
# ==============================================================================
# Alles innerhalb von 'with st.sidebar:' wandert in das ausklappbare Seitenmenü.
with st.sidebar:
    st.header("📊 Leistungszustand")
    if "leistungsstatus" in st.session_state and st.session_state.leistungsstatus:
        status = st.session_state.leistungsstatus
        st.caption(f"Letztes Update: {status.get('letztes_update', '---')}")
        st.metric("Geschätzter VO2max", f"⚡ {status.get('vo2max', '---')}")
        st.markdown("**🎯 Laufprognosen:**")
        st.markdown(f"• **5 km:** {status.get('prognose_5k', '---')}")
        st.markdown(f"• **10 km:** {status.get('prognose_10k', '---')}")
        st.markdown(f"• **21 km:** {status.get('prognose_21k', '---')}")
        st.markdown(f"🔥 **Belastung:**\n`{status.get('belastung', '---')}`")
    else:
        st.info("Noch kein Leistungsstatus im Browser-Speicher.")
        
    st.divider()
    st.header("👟 Letzte Aktivitäten")
    if "leistungsstatus" in st.session_state and st.session_state.leistungsstatus and st.session_state.leistungsstatus.get("letzte_aktivitaeten"):
        for act in st.session_state.leistungsstatus.get("letzte_aktivitaeten"): st.write(act)
    elif "last_three_activities" in st.session_state:
        for act in st.session_state.last_three_activities: st.write(act)
        
    st.divider()
    # Der rote Panik-Button: Löscht radikal alle Cookies und leert den Session State
    if st.sidebar.button("⚠️ Lokale Daten löschen", key="btn_clear_device_data"):
        cookie_manager.delete("auth_paket")
        cookie_manager.delete("physio_paket")
        cookie_manager.delete("app_backup_paket")
        for key in ["messages", "strava_context", "doc_names", "doc_texts", "doc_images", "temp_auth_data", "trainingsplan", "wochenplan", "leistungsstatus", "last_three_activities"]:
            if key in st.session_state: del st.session_state[key]
        time.sleep(0.5)
        st.rerun() # Zwingt Streamlit zu einem sofortigen, sauberen Neu-Zeichnen der Seite


# ==============================================================================
# 🔑 SCHLEUSE (LOGIN ODER HAUPT-APP)
# ==============================================================================
# Hier wird entschieden: Sieht der Nutzer das Login-Menü oder die eigentliche App?
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
# 🏃‍♂️ HAUPT-APP BEREICH (NUR FÜR EINGELOGGTE NUTZER)
# ==============================================================================
else:
    # Wir wecken das Google GenAI Client-Modul auf und übergeben deinen Schlüssel
    client = genai.Client(api_key=gemini_key)
    if "temp_auth_data" in st.session_state:
        cookie_manager.set("auth_paket", json.dumps(st.session_state.temp_auth_data), key="cookie_set_main_auth")

    # --- DATEN-BACKUP MENÜ (EXPENDER) ---
    with st.expander("💾 App-Daten sichern & wiederherstellen (Gegen Server-Reset)"):
        st.caption("Falls der Server deine Pläne gelöscht hat, kannst du hier dein Backup einspielen oder den aktuellen Stand sichern.")
        c_exp, c_imp = st.columns(2)
        with c_exp:
            current_backup = {
                "trainingsplan": st.session_state.get("trainingsplan", ""),
                "wochenplan": st.session_state.get("wochenplan", ""),
                "leistungsstatus": st.session_state.get("leistungsstatus", {})
            }
            st.download_button("📥 Backup-Datei herunterladen", data=json.dumps(current_backup, indent=2, ensure_ascii=False), file_name="trainer_backup.json", mime="application/json")
        with c_imp:
            uploaded_backup = st.file_uploader("📤 Backup-Datei hochladen", type=["json"], key="upload_backup_file")
            if st.button("🔄 Daten aus Datei wiederherstellen", key="btn_trigger_import"):
                if uploaded_backup:
                    try:
                        b_content = json.load(uploaded_backup)
                        save_all_to_state_and_cookies(b_content.get("trainingsplan"), b_content.get("wochenplan"), b_content.get("leistungsstatus"))
                        st.success("Backup erfolgreich geladen!")
                        st.rerun()
                    except Exception as e: st.error(f"Fehler beim Laden: {e}")

    # --- TRAINER-INSTRUCTION MENÜ ---
    with st.expander("🧠 Trainer-Instruktionen"):
        new_instructions = st.text_area("Anweisungen", value=trainer_instructions, height=150, key="input_instructions")
        if st.button("💾 Speichern", key="btn_save_instructions"):
            physio_data["instructions"] = new_instructions
            cookie_manager.set("physio_paket", json.dumps(physio_data), key="cookie_set_instructions")
            st.success("Gespeichert!")

    # --- PHYSIO MENÜ ---
    with st.expander("📊 Physiologische Werte"):
        col_v, col_l, col_b = st.columns(3)
        with col_v: new_vo2max = st.text_input("VO2max Basis", value=vo2max, key="input_vo2max")
        with col_l: new_laktat = st.text_input("Laktatschwelle", value=laktat, key="input_laktat")
        with col_b: new_belastung = st.text_input("Fokus-Belastung", value=belastung, key="input_belastung")
        if st.button("💾 Werte speichern", key="btn_save_physio"):
            physio_data.update({"vo2max": new_vo2max, "laktat": new_laktat, "belastung": new_belastung})
            cookie_manager.set("physio_paket", json.dumps(physio_data), key="cookie_set_physio_values")
            st.success("Gespeichert!")

    # --- DATEI MANAGER ---
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

    # --- ANZEIGE DER ERGEBNISSE ---
    with st.expander("📅 Aktueller Wochenplan", expanded=bool(st.session_state.get("wochenplan"))):
        if st.session_state.get("wochenplan"):
            st.markdown(st.session_state.wochenplan)
            st.divider()
            st.download_button("📥 Wochenplan speichern (.md)", data=st.session_state.wochenplan, file_name="wochenplan.md", mime="text/markdown", key="dl_wp")
        else:
            st.info("Kein Wochenplan vorhanden. Klicke unten auf 'Wochenplan & Status aktualisieren'!")

    with st.expander("🏆 Langfristiger Masterplan", expanded=False):
        if st.session_state.get("trainingsplan"):
            st.markdown(st.session_state.trainingsplan)
            st.divider()
            st.download_button("📥 Masterplan (.md)", data=st.session_state.trainingsplan, file_name="trainingsplan.md", mime="text/markdown", key="dl_mp_md")
        else:
            st.info("Kein langfristiger Masterplan vorhanden. Generiere zuerst deinen großen Masterplan.")


    # ==============================================================================
    # 💥 DIE KI-STEUERZENTRALE (BUTTONS & PROMPTS)
    # ==============================================================================
    st.divider()
    st.subheader("🗓️ Trainingspläne & Status steuern")
    
    # --- DYNAMISCHER ZEITANKER ---
    # Hier liest Python das EXAKTE heutige Datum deines Systems aus (z.B. Montag, 15. Juni 2026)
    heute_iso = datetime.now().strftime("%A, %d. %B %Y")
    
    # Diesen Textblock weben wir jetzt in JEDE KI-Anfrage ein. Es ist der absolute Befehl,
    # dass die KI nicht in der Vergangenheit herumgeistern darf.
    zeit_befehl = f"""
    ⚠️ WICHTIGER SYSTEM-ZEITANKER:
    Heute ist exakt der {heute_iso}. Wir befinden uns im Jahr 2026!
    Jedes Strava-Training mit einem Datum aus 2026 ist brandaktuell.
    Der Marathon-Wettkampf ist am Sonntag, den 05.07.2026 – also in wenigen Wochen!
    Rechne alle Pläne und Tapering-Wochen penibel von diesem heutigen Datum ({heute_iso}) rückwärts oder vorwärts. 
    Behandle das aktuelle Jahr NIEMALS als 2024 oder ein anderes Jahr.
    """

    # --- KNOPF A: INITIALER MASTERPLAN ---
    if not st.session_state.get("trainingsplan"):
        if st.button("✨ Großen Masterplan initial erstellen (lädt Strava-Daten)", key="btn_new_plan"):
            with st.spinner("Lade aktuelle Strava-Daten und erstelle langfristigen Masterplan..."):
                if load_and_format_strava_data():
                    # Wir bündeln den Zeitbefehl mit dem echten Prompt
                    prompt = f"{zeit_befehl}\n\nErstelle einen neuen langfristigen Masterplan bis zum Marathon am 05.07.2026.\nHistorie:\n{st.session_state.strava_context}\nInstruktionen: {trainer_instructions}\n"
                    try:
                        # Hier feuern wir den Befehl über das SDK ab und warten auf die Antwort (resp.text)
                        resp = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt] + st.session_state.doc_images)
                        if resp.text:
                            save_all_to_state_and_cookies(plan_text=resp.text)
                            st.success("Masterplan erfolgreich erstellt!")
                            st.rerun()
                    except Exception as e: st.error(f"Fehler: {e}")
    else:
        # --- KNOPF B & C: DIE UPDATES ---
        c_wp, c_mp = st.columns(2)
        with c_wp:
            if st.button("📅 Wochenplan & Status aktualisieren (lädt Strava-Daten)", key="btn_update_woche"):
                with st.spinner("Hole Strava-Daten und berechne adaptiven Wochenplan..."):
                    if load_and_format_strava_data():
                        # Der mächtige "Alles-In-Einem"-Prompt mit dem eingebauten Zeitanker
                        prompt = f"""
                        {zeit_befehl}
                        
                        Du bist der persönliche KI-Laufcoach des Athleten.
                        Hier ist der aktuelle langfristige Masterplan:
                        {st.session_state.trainingsplan}
                        
                        Hier sind die neuesten Strava-Trainingsdaten:
                        {st.session_state.strava_context}
                        
                        Instruktionen:
                        {trainer_instructions}
                        
                        Physiologische Werte: VO2max: {vo2max}, Laktat: {laktatschwelle}, Belastung: {belastung}
                        
                        AUFGABE:
                        1. Erstelle einen adaptiven Wochenplan für den Rest DIESER aktuellen Woche (basierend auf dem heutigen Stand: {heute_iso}). Passe ihn intelligent an, falls zusätzliche Aktivitäten (Radtouren) erfolgten oder Einheiten verändert wurden.
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
                            # Die App zerschneidet den Text der KI anhand der definierten Trenn-Marker (Split)
                            if "===STATUS_START===" in text and "===WOCHENPLAN_START===" in text:
                                status_part = text.split("===STATUS_START===")[1].split("===STATUS_END===")[0].strip()
                                woche_part = text.split("===WOCHENPLAN_START===")[1].split("===WOCHENPLAN_END===")[0].strip()
                                
                                s_json = {}
                                try:
                                    s_json = json.loads(status_part)
                                    s_json["letzte_aktivitaeten"] = st.session_state.get("last_three_activities", [])
                                    s_json["letztes_update"] = datetime.now().strftime("%d.%m.%Y")
                                except: pass
                                    
                                save_all_to_state_and_cookies(woche_text=woche_part, status_json=s_json)
                                st.success("Wochenplan & Leistungsstatus erfolgreich aktualisiert!")
                                st.rerun()
                        except Exception as e: st.error(f"Fehler: {e}")
        
        with c_mp:
            if st.button("🏆 Masterplan aktualisieren (lädt Strava-Daten)", key="btn_update_master"):
                with st.spinner("Hole Strava-Daten und aktualisiere großen Masterplan..."):
                    if load_and_format_strava_data():
                        prompt = f"{zeit_befehl}\n\nHier ist mein alter Masterplan:\n{st.session_state.trainingsplan}\n\nHier sind neue Trainingsdaten:\n{st.session_state.strava_context}\n\nInstruktionen:\n{trainer_instructions}\n\nSchreibe den großen Masterplan intelligent bis zum 05.07.2026 neu."
                        try:
                            resp = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt] + st.session_state.doc_images)
                            if resp.text:
                                save_all_to_state_and_cookies(plan_text=resp.text)
                                st.success("Langfristiger Masterplan erfolgreich aktualisiert!")
                                st.rerun()
                        except Exception as e: st.error(f"Fehler: {e}")


    # ==============================================================================
    # 💬 CHAT-INTERFAZ (COACH TALK)
    # ==============================================================================
    st.divider()
    st.subheader("💬 Chat mit Coach")
    # Zeige alle bisherigen Nachrichten aus der Session-Historie auf dem Bildschirm an
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    # st.chat_input erstellt die Eingabezeile am unteren Bildschirmrand
    if user_input := st.chat_input("Nachricht an den Coach..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"): st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Tippt..."):
                # Auch im Chat bekommt der Coach vorab den Zeitanker umgehängt
                prompt = f"{zeit_befehl}\n\nDu bist Coach. Plan:\n{st.session_state.get('wochenplan', st.session_state.get('trainingsplan'))}\nDaten:\n{st.session_state.strava_context}\nFrage: {user_input}"
                try:
                    resp = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt] + st.session_state.doc_images)
                    if resp.text:
                        st.markdown(resp.text)
                        st.session_state.messages.append({"role": "assistant", "content": resp.text})
                except Exception as e: st.error(f"Fehler: {e}")
