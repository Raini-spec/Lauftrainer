# ==============================================================================
# 📦 BIBLIOTHEKEN LADEN (IMPORT-BEREICH)
# ==============================================================================
import streamlit as st
import requests 
from google import genai 
import time 
from datetime import datetime, timedelta
import json 
import PyPDF2
from PIL import Image 
from supabase import create_client, Client
import extra_streamlit_components as stx 

st.set_page_config(page_title="KI Trainer", layout="centered")
cookie_manager = stx.CookieManager()
st.write("") 

st.title("🏃‍♂️🚴 KI Trainer: Strava & Gemini")
st.caption("🔒 **Version 5.02** – Bugfix Supabase-URL & Dropdown-Menü")

# ==============================================================================
# 🧠 SESSION STATE & CLOUD DATABASE (SUPABASE)
# ==============================================================================
if "messages" not in st.session_state: st.session_state.messages = []
if "strava_context" not in st.session_state: st.session_state.strava_context = ""
if "letzte_10_aktivitaeten" not in st.session_state: st.session_state.letzte_10_aktivitaeten = []
if "doc_names" not in st.session_state: st.session_state.doc_names = []
if "doc_texts" not in st.session_state: st.session_state.doc_texts = []
if "doc_images" not in st.session_state: st.session_state.doc_images = []
if "gym_images" not in st.session_state: st.session_state.gym_images = []
if "plan_images" not in st.session_state: st.session_state.plan_images = []
if "doc_texts" not in st.session_state: st.session_state.doc_texts = []    
if "ansicht" not in st.session_state: st.session_state.ansicht = "Wochenplan"
if "physio_data" not in st.session_state: st.session_state.physio_data = {}

auth_cookie = cookie_manager.get("auth_paket")
auth_data = json.loads(auth_cookie) if isinstance(auth_cookie, str) else (auth_cookie or {})
if "temp_auth_data" in st.session_state: auth_data = st.session_state.temp_auth_data

try:
    # AUTOMATISCHER BUGFIX: Entfernt versehentliche Schrägstriche am Ende der URL
    clean_url = st.secrets["SUPABASE_URL"].rstrip("/")
    supabase: Client = create_client(clean_url, st.secrets["SUPABASE_KEY"])
except Exception as e:
    st.error("Datenbankverbindung konnte nicht hergestellt werden. Bitte Secrets prüfen.")

def load_all_from_supabase():
    username = auth_data.get("master_pw", "default_user")
    try:
        response = supabase.table("trainer_daten").select("schluessel, wert").eq("username", username).execute()
        rows = response.data
        if rows:
            for row in rows:
                schluessel = row["schluessel"]
                wert = row["wert"]
                
                if schluessel == "trainingsplan": st.session_state.trainingsplan = wert
                elif schluessel == "wochenplan": st.session_state.wochenplan = wert
                elif schluessel == "heute_training": st.session_state.heute_training = wert
                elif schluessel == "morgen_training": st.session_state.morgen_training = wert
                elif schluessel == "leistungsstatus":
                    try: st.session_state.leistungsstatus = json.loads(wert)
                    except: pass
                elif schluessel == "physio_paket":
                    try: st.session_state.physio_data = json.loads(wert)
                    except: pass
    except Exception as e:
        pass

def save_all_to_supabase(plan_text=None, woche_text=None, status_json=None, heute_text=None, morgen_text=None):
    if plan_text is not None: st.session_state.trainingsplan = plan_text
    if woche_text is not None: st.session_state.wochenplan = woche_text
    if status_json is not None: st.session_state.leistungsstatus = status_json
    if heute_text is not None: st.session_state.heute_training = heute_text
    if morgen_text is not None: st.session_state.morgen_training = morgen_text

    username = auth_data.get("master_pw", "default_user")
    
    try:
        daten_aktuell = {
            "trainingsplan": st.session_state.get("trainingsplan", ""),
            "wochenplan": st.session_state.get("wochenplan", ""),
            "heute_training": st.session_state.get("heute_training", ""),
            "morgen_training": st.session_state.get("morgen_training", ""),
            "leistungsstatus": json.dumps(st.session_state.get("leistungsstatus", {})),
            "physio_paket": json.dumps(st.session_state.get("physio_data", {}))
        }
        
        for k, v in daten_aktuell.items():
            supabase.table("trainer_daten").delete().eq("username", username).eq("schluessel", k).execute()
            supabase.table("trainer_daten").insert({"username": username, "schluessel": k, "wert": v}).execute()
        return True    
    except Exception as e:
        st.error(f"Fehler beim Speichern in der Cloud-Datenbank: {e}")
        return False
if gemini_key := auth_data.get("gemini_key"):
    if "trainingsplan" not in st.session_state:
        load_all_from_supabase()

# ==============================================================================
# ⚙️ HILFSFUNKTIONEN
# ==============================================================================
def get_valid_strava_token():
    global auth_data
    expires_at = auth_data.get("expires_at")
    if not expires_at or time.time() > (float(expires_at) - 300):
        with st.spinner("Erneuere Strava-Zugriff..."):
            res = requests.post("https://www.strava.com/oauth/token", data={
                "client_id": auth_data.get("client_id"),
                "client_secret": auth_data.get("client_secret"),
                "refresh_token": auth_data.get("refresh_token"),
                "grant_type": "refresh_token"
            })
            if res.status_code == 200:
                data = res.json()
                auth_data.update({"access_token": data["access_token"], "refresh_token": data["refresh_token"], "expires_at": data["expires_at"]})
                cookie_manager.set("auth_paket", json.dumps(auth_data), key="cookie_set_refresh")
                return data["access_token"]
            return None
    return auth_data.get("access_token")

def load_and_format_strava_data():
    strava_token = get_valid_strava_token()
    if not strava_token: return False
    try:
        res = requests.get(f"https://www.strava.com/api/v3/athlete/activities?per_page=30", headers={"Authorization": f"Bearer {strava_token}"})
        if res.status_code == 200:
            activities = res.json()
            if activities:
                data = ""
                last_ten = []
                for act in activities:
                    t = act.get('sport_type', act.get('type', 'Unbekannt'))
                    d = act.get('distance', 0) / 1000
                    s = act.get('average_speed', 0)
                    date = act.get('start_date_local', '')[:10]
                    p = act.get('average_heartrate', 'Kein Puls')
                    t_de = "Lauf" if t in ["Run", "Lauf"] else ("Radfahren" if t in ["Ride", "Cycling"] else t)
                    if t in ["Run", "Lauf"] and s > 0:
                        pace_gesamt_sekunden = int(1000 / s)
                        mins, secs = divmod(pace_gesamt_sekunden, 60)
                        info = f"Pace: {mins}.{secs:02d} min/km"
                    else:
                        info = f"Geschw.: {s*3.6:.2f} km/h"
                    data += f"- [{date}] [{t}] {act.get('name')}: {d:.2f} km | {info} | Ø Puls: {p}\n"
                    
                    if len(last_ten) < 10:
                        try: dt_str = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m.%y")
                        except: dt_str = date
                        last_ten.append(f"**{dt_str}** | {t_de}: {d:.1f} km *({info})*")
                        
                # NEU: Gym-Historie für die KI an die Strava-Daten anhängen!
                gym_hist = st.session_state.physio_data.get("gym_history", [])
                if gym_hist:
                    data += "\n--- MANUELLE GYM-EINHEITEN ---\n" + "\n".join(gym_hist)
                        
                st.session_state.strava_context = data
                st.session_state.letzte_10_aktivitaeten = last_ten
                return True
        return False
    except: return False

def ask_gemini_with_retry(client, prompt, images=[], max_retries=3):
    alle_bilder = images + st.session_state.get("gym_images", []) + st.session_state.get("plan_images", [])
    
    # NEU: Der KI genau sagen, was die Anhänge bedeuten!
    if st.session_state.get("gym_images"):
        prompt += "\n\n⚠️ WICHTIGER HINWEIS ZU DEN BILDERN: Die angehängten Bilder zeigen zusätzliche Krafttrainingseinheiten inklusive verbrauchter Kalorien und spezifischer Übungen (siehe extrahierte Daten in den Aktivitäten). Berücksichtige diese Übungen und die zusätzliche muskuläre Belastung exakt bei der Regeneration und der Anpassung der kommenden Laufeinheiten im Wochenplan!"
    
    if st.session_state.get("plan_images") or st.session_state.get("doc_texts"):
        prompt += "\n\n⚠️ WICHTIGER HINWEIS ZU DEN DOKUMENTEN: Die angehängten Dokumente (Texte/Bilder) sind meine bisherigen Trainingspläne oder sportlichen Vorgaben. Nutze diese als starke Orientierung oder Basis für deine eigene Planung!"

    if st.session_state.get("doc_texts"):
        prompt += "\n\nHier ist der Text aus den hochgeladenen PDFs:\n" + "\n".join(st.session_state.doc_texts)
        
    last_error = None
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt] + alle_bilder)
            return resp.text
        except Exception as e:
            last_error = e
            if "503" in str(e) or "429" in str(e):
                time.sleep(3)
                continue
            else:
                raise e
    raise last_error

# ==============================================================================
# 🎛️ COCKPIT LINKS (STREAMLIT SIDEBAR)
# ==============================================================================
with st.sidebar:
    st.header("🧭 Navigation")
    if st.button("📅 Aktueller Wochenplan", use_container_width=True): st.session_state.ansicht = "Wochenplan"
    if st.button("🏆 Masterplan", use_container_width=True): st.session_state.ansicht = "Masterplan"
    if st.button("👟 Letzte Aktivitäten & Workoutanalyse", use_container_width=True): st.session_state.ansicht = "Aktivitäten"
    if st.button("⚙️ Trainerinstruktionen & Setup", use_container_width=True): st.session_state.ansicht = "Einstellungen"
    if st.button("📊 Lauf-Statistiken & Prognosen", use_container_width=True): st.session_state.ansicht = "Statistiken"
    st.divider()

    st.header("📊 Leistungszustand")
    if "leistungsstatus" in st.session_state and st.session_state.leistungsstatus:
        status = st.session_state.leistungsstatus
        st.caption(f"Letztes Update: {status.get('letztes_update', '---')}")
        st.metric("Geschätzter VO2max", f"⚡ {status.get('vo2max', '---')}")
        
        st.info("ℹ️ **Hinweis:** Dieser Wert ist eine KI-Schätzung. Ein lang anhaltender Anstieg liegt oft an einem anfangs zu gering geschätzten Startwert.")
        
        st.markdown("**🎯 Gemini-Prognosen:**")
        st.markdown(f"🥇 **5 km:** &nbsp;&nbsp; `{status.get('prognose_5k', '---')}`")
        st.markdown(f"🥈 **10 km:** &nbsp; `{status.get('prognose_10k', '---')}`")
        st.markdown(f"🥉 **21 km:** &nbsp; `{status.get('prognose_21k', '---')}`")
        
        st.write("")
        st.markdown("**🔥 Akute Belastung:**")
        belastung_text = status.get('belastung', 'Niedrig')
        raw_b = status.get("belastung_prozent", 20)
        try: belastung_prozent = int(float(str(raw_b).replace("%", "").strip()))
        except: belastung_prozent = 20
        
        color_code = "#2ecc71" if belastung_prozent < 45 else "#f1c40f" if belastung_prozent < 75 else "#e74c3c"
        st.markdown(f"""
            <div style="width: 100%; background-color: #f0f2f6; border-radius: 4px; height: 8px; margin-bottom: 4px;">
                <div style="width: {belastung_prozent}%; background-color: {color_code}; height: 8px; border-radius: 4px;"></div>
            </div>
            <span style="font-size: 0.85rem; color: #555;">Status: <i>{belastung_text} ({belastung_prozent}%)</i></span>
        """, unsafe_allow_html=True)
    else:
        st.info("Kein aktiver Leistungsstatus im Speicher.")

    st.divider()
    if st.button("⚠️ App-Reset (Alle Daten löschen)", use_container_width=True, type="primary"):
        cookie_manager.delete("auth_paket")
        st.session_state.clear()
        time.sleep(0.5)
        st.rerun()

# ==============================================================================
# 🔑 SCHLEUSE (LOGIN ODER VOLLSTÄNDIGES SETUP ZUM TEILEN)
# ==============================================================================
access_token = auth_data.get("access_token")
gemini_key = auth_data.get("gemini_key")

if not gemini_key or not access_token:
    st.info("👋 Willkommen! Bitte einloggen oder App neu einrichten.")
    tab1, tab2 = st.tabs(["📁 Login (Datei)", "⌨️ Manuelle Einrichtung"])
    
    with tab1:
        config_file = st.file_uploader("Konfigurations-Datei (.json)", type=["json"])
        master_pw = st.text_input("Master-Passwort", type="password", key="login_pw")
        if st.button("🔐 Entsperren"):
            if config_file and master_pw:
                content = json.load(config_file)
                if content.get("master_pw") == master_pw:
                    st.session_state.temp_auth_data = content
                    st.rerun()
                else: st.error("Passwort falsch.")
                
    with tab2:
        st.write("⚙️ **App-Einrichtung für dich oder neue Nutzer:**")
        in_pw = st.text_input("🔑 Wähle dein Master-Passwort", type="password", key="setup_pw")
        in_gemini = st.text_input("1. Gemini API Key", type="password", key="setup_gemini")
        in_client_id = st.text_input("2. Strava Client-ID", key="setup_id")
        in_client_secret = st.text_input("3. Geheimer Clientschlüssel", type="password", key="setup_secret")
        
        if in_client_id:
            auth_url = f"https://www.strava.com/oauth/authorize?client_id={in_client_id}&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=activity:read_all"
            st.markdown(f"[👉 Klicke hier, um Strava freizugeben]({auth_url})")
            
        in_code = st.text_input("4. Kopiere den Code aus der Adresszeile (nach dem Autorisieren) hier hinein", key="setup_code")
        
        if st.button("🚀 App aktivieren & Konfiguration erstellen", key="btn_setup"):
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
                    st.success("App erfolgreich konfiguriert!")
                    
        if "auto_config_json" in st.session_state:
            st.download_button("📥 JETZT CONFIG.JSON HERUNTERLADEN", data=st.session_state["auto_config_json"], file_name="config.json", mime="application/json")
            if st.button("🔄 App jetzt starten", key="btn_start_after_setup"):
                st.session_state.temp_auth_data = json.loads(st.session_state["auto_config_json"])
                st.rerun()

# ==============================================================================
# 🏃‍♂️ HAUPT-APP BEREICH (DYNAMISCH)
# ==============================================================================
else:
    tage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    monate = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
    jetzt = datetime.now() + timedelta(hours=2)
    heute_str = f"{tage[jetzt.weekday()]}, der {jetzt.day}. {monate[jetzt.month - 1]} {jetzt.year}"
    
    zeit_befehl = f"⚠️ WICHTIGER SYSTEM-ZEITANKER:\nHeute ist exakt {heute_str}!! Das ist die unumstößliche Realität."
    
    client = genai.Client(api_key=gemini_key)
    if "temp_auth_data" in st.session_state:
        cookie_manager.set("auth_paket", json.dumps(st.session_state.temp_auth_data), key="cookie_set_main_auth")

    output_format_alle = """
    ===STATUS_START===
    {"vo2max": "Zahl", "prognose_5k": "Zeit", "prognose_10k": "Zeit", "prognose_21k": "Zeit", "belastung": "Kurzer Text", "belastung_prozent": "Zahl 0-100"}
    ===STATUS_END===
    ===HEUTE_START===\nHier steht nur die heutige Einheit in 1-2 Sätzen.\n===HEUTE_END===
    ===MORGEN_START===\nHier steht nur die morgige Einheit in 1-2 Sätzen.\n===MORGEN_END===
    ===WOCHENPLAN_START===\n### 📅 Dein adaptiver Wochenplan\n*Markdown-Plan...*\n===WOCHENPLAN_END===
    """

    # Kontext auslesen für KI
    ziel_typ = st.session_state.physio_data.get("ziel_typ", "Formaufbau")
    trainer_instructions = st.session_state.physio_data.get("instructions", "Keine speziellen Anweisungen.")
    aktueller_vo2max = st.session_state.get('leistungsstatus', {}).get('vo2max', 'Nicht berechnet')
    
    ziel_kontext = f"**Trainingsziel:** {ziel_typ}\n"
    if ziel_typ == "Spezielles Wettkampf-Event":
        ziel_kontext += f"**Event-Name:** {st.session_state.physio_data.get('event_name', '?')}\n"
        ziel_kontext += f"**Event-Datum:** {st.session_state.physio_data.get('event_datum', '?')}\n"
        ziel_kontext += f"**Geplante Distanz:** {st.session_state.physio_data.get('distanz', '?')}\n"
        ziel_kontext += f"**Angestrebte Zielzeit:** {st.session_state.physio_data.get('zielzeit', '?')}\n"

    # --- ANSICHT: WOCHENPLAN ---
    # --- ANSICHT: WOCHENPLAN ---
    if st.session_state.ansicht == "Wochenplan":
        st.header("📅 Aktueller Wochenplan")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.session_state.get("heute_training"):
                st.success(f"🎯 **HEUTE:**\n\n{st.session_state.heute_training}")
        with c2:
            if st.session_state.get("morgen_training"):
                st.info(f"⏭️ **MORGEN:**\n\n{st.session_state.morgen_training}")

        if st.session_state.get("wochenplan"):
            st.markdown(st.session_state.wochenplan)
            
            # HIER SETZT DER NEUE CODE EIN (Eingerückt mit 8 Leerzeichen):
            if st.button("🔄 Nur Wochenplan aktualisieren", type="primary"):
                if load_and_format_strava_data():
                    try:
                        with st.spinner("Aktualisiere Wochenplan..."):
                            tage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
                            monate = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
                            jetzt = datetime.now() + timedelta(hours=2)
                            heute_str = f"{tage[jetzt.weekday()]}, der {jetzt.day}. {monate[jetzt.month - 1]} {jetzt.year}"
                            
                            zeit_befehl = f"⚠️ WICHTIGER SYSTEM-ZEITANKER:\nHeute ist exakt {heute_str}!! Das ist die unumstößliche Realität."
                            
                            client = genai.Client(api_key=gemini_key)
                            
                            prompt_woche = f"""
                            {zeit_befehl}
                            🚨 DATUMS-REGEL: Die untenstehenden Strava-Daten sind HISTORIE der Vergangenheit! Leite den heutigen Tag AUSSCHLIESSLICH aus dem SYSTEM-ZEITANKER ab.
                            
                            Basierend auf diesem Masterplan:\n{st.session_state.get('trainingsplan', '')}
                            Strava-Historie:\n{st.session_state.strava_context}
                            Ziel & Event:\n{ziel_kontext}
                            
                            AUFGABE:
                            1. Erstelle den adaptiven Wochenplan für den Rest DIESER Woche.
                            2. Extrahiere die heutige und morgige Einheit.
                            3. Berechne den Leistungszustand.
                            
                            VO2MAX-REGEL: Der letzte berechnete VO2max war {aktueller_vo2max}. Passe ihn basierend auf den neuen Strava-Daten maximal um +/- 0.5 Punkte an (Glättung). Wenn er 'Nicht berechnet' ist, schätze ihn realistisch ein.
                            
                            {output_format_alle}
                            """
                            
                            text = ask_gemini_with_retry(client, prompt_woche)
                            
                            w_part = text.split("===WOCHENPLAN_START===")[1].split("===WOCHENPLAN_END===")[0].strip() if "===WOCHENPLAN_START===" in text else ""
                            h_part = text.split("===HEUTE_START===")[1].split("===HEUTE_END===")[0].strip() if "===HEUTE_START===" in text else ""
                            m_part = text.split("===MORGEN_START===")[1].split("===MORGEN_END===")[0].strip() if "===MORGEN_START===" in text else ""
                            status_part = text.split("===STATUS_START===")[1].split("===STATUS_END===")[0].strip() if "===STATUS_START===" in text else "{}"
                            
                            s_json = json.loads(status_part) if "vo2max" in status_part else {}
                            s_json["letztes_update"] = datetime.now().strftime("%d.%m.%Y")
                            
                            save_all_to_supabase(plan_text=st.session_state.get('trainingsplan', ''), woche_text=w_part, status_json=s_json, heute_text=h_part, morgen_text=m_part)
                            st.success("Wochenplan erfolgreich aktualisiert!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Fehler: {e}")
        else:
            st.info("Kein Wochenplan vorhanden. Generiere zuerst deinen großen Masterplan!")

    # --- ANSICHT: MASTERPLAN ---

    # --- ANSICHT: MASTERPLAN ---
    elif st.session_state.ansicht == "Masterplan":
        st.header("🏆 Langfristiger Masterplan")
        if not st.session_state.physio_data.get("ziel_typ"):
            st.warning("⚠️ Du hast noch kein Trainingsziel festgelegt. Der Plan wird auf 'Formaufbau' standardisiert. Unter '⚙️ Trainerinstruktionen' kannst du dies ändern.")
            
        if st.session_state.get("trainingsplan"):
            st.markdown(st.session_state.trainingsplan)
            
        if st.button("🔄 Masterplan generieren / aktualisieren", type="primary"):
            if load_and_format_strava_data():
                try:
                    with st.spinner("Schritt 1/2: Erstelle langfristigen Masterplan..."):
                        prompt_master = f"""
                        {zeit_befehl}
                        Hier sind meine Strava-Daten:
                        {st.session_state.strava_context}
                        
                        Ziel & Event-Kontext:
                        {ziel_kontext}
                        
                        Instruktionen:
                        {trainer_instructions}
                        
                        AUFGABE:
                        Erstelle AUSSCHLIESSLICH den großen, langfristigen Masterplan im Markdown-Format. Richte den Plan zwingend auf das angegebene Trainingsziel aus! Fasse dich prägnant, konzentriere dich auf die Wochenstruktur.
                        """
                        mp_part = ask_gemini_with_retry(client, prompt_master, st.session_state.doc_images)
                    
                with st.spinner("Schritt 2/2: Leite Wochenplan ab und synchronisiere Cloud-Tabelle..."):
                    prompt_woche = f"""
                    {zeit_befehl}
                    🚨 DATUMS-REGEL: Die untenstehenden Strava-Daten sind HISTORIE der Vergangenheit! Leite den heutigen Tag AUSSCHLIESSLICH aus dem SYSTEM-ZEITANKER ab.
                    
                    Basierend auf diesem Masterplan:\n{mp_part}
                    Strava-Historie:\n{st.session_state.strava_context}
                    Ziel & Event:\n{ziel_kontext}
                    
                    AUFGABE:
                    1. Erstelle den adaptiven Wochenplan für den Rest DIESER Woche.
                    2. Extrahiere die heutige und morgige Einheit.
                    3. Berechne den Leistungszustand.
                    
                    VO2MAX-REGEL: Der letzte berechnete VO2max war {aktueller_vo2max}. Passe ihn basierend auf den neuen Strava-Daten maximal um +/- 0.5 Punkte an (Glättung). Wenn er 'Nicht berechnet' ist, schätze ihn realistisch ein.
                    
                    {output_format_alle}
                    """
                    text = ask_gemini_with_retry(client, prompt_woche)
                    
                    w_part = text.split("===WOCHENPLAN_START===")[1].split("===WOCHENPLAN_END===")[0].strip() if "===WOCHENPLAN_START===" in text else ""
                    h_part = text.split("===HEUTE_START===")[1].split("===HEUTE_END===")[0].strip() if "===HEUTE_START===" in text else ""
                    m_part = text.split("===MORGEN_START===")[1].split("===MORGEN_END===")[0].strip() if "===MORGEN_START===" in text else ""
                    status_part = text.split("===STATUS_START===")[1].split("===STATUS_END===")[0].strip() if "===STATUS_START===" in text else "{}"
                    
                    s_json = json.loads(status_part) if "vo2max" in status_part else {}
                    s_json["letztes_update"] = datetime.now().strftime("%d.%m.%Y")
                    
                    save_all_to_supabase(plan_text=mp_part, woche_text=w_part, status_json=s_json, heute_text=h_part, morgen_text=m_part)
                    st.success("Plan erfolgreich erstellt und in Supabase gesichert!")
                    st.rerun()
                except Exception as e: 
                    st.error(f"Fehler bei KI-Verarbeitung: {e}")
            else: 
                st.error("Konnte Strava-Daten nicht laden.")

    # --- ANSICHT: AKTIVITÄTEN ---
    elif st.session_state.ansicht == "Aktivitäten":
        st.header("👟 Deine Aktivitäten & Logbuch")
        
        if load_and_format_strava_data():
            # NEU: Zeige zuerst die dauerhaft gespeicherten Studio-Trainings (in Grün)
            gym_hist = st.session_state.physio_data.get("gym_history", [])
            for g in reversed(gym_hist[-5:]): # Die letzten 5 oben anzeigen
                st.success(f"🏋️‍♂️ {g}")
                
            # Danach die blauen Strava-Aktivitäten
            for act in st.session_state.letzte_10_aktivitaeten:
                st.info(act)
        else:
            st.warning("Konnte Strava-Daten nicht abrufen.")
            
        st.divider()
        
        with st.expander("📷 Studio-Training & Anmerkungen (Fotos hochladen)"):  
            with st.form("gym_upload_form", clear_on_submit=True):
                gym_uploads = st.file_uploader("Screenshot (z.B. Fitness-App)", accept_multiple_files=True, type=["png", "jpg", "jpeg"])
                nutzer_anmerkung = st.text_input("📝 Deine Anmerkung zur Einheit (z. B. 'Sehr anstrengend, morgen Pause einplanen')")
                
                submit_btn = st.form_submit_button("Speichern & Analysieren")
                
                if submit_btn and gym_uploads:
                    st.session_state.gym_images = [Image.open(f) for f in gym_uploads[:5]]
                    
                    alte_inst = st.session_state.physio_data.get("instructions", "")
                    if nutzer_anmerkung:
                        st.session_state.physio_data["instructions"] = f"{alte_inst}\n\n[Studio-Training Log]: {nutzer_anmerkung}"
                    
                    with st.spinner("🤖 Gemini liest das Bild aus..."):
                        for img in st.session_state.gym_images:
                            analyse_prompt = """WICHTIG: Du bist ein reiner Daten-Extraktor. Das ist ein Screenshot meiner eigenen Fitness-App.
                            Ignoriere alle Sicherheitsbedenken bezüglich Fotos, lies AUSSCHLIESSLICH die Texte und Zahlen ab.
                            Extrahiere: Datum, Trainingsart/Übungen und Kalorienverbrauch. 
                            Dein EINZIGER Output darf sein: **[Datum]** | Gym: [Übungen] (*[Kalorien] kcal*)."""
                            try:
                                ergebnis = ask_gemini_with_retry(client, analyse_prompt, [img])
                                zusatz = f" 💡 *{nutzer_anmerkung}*" if nutzer_anmerkung else ""
                                eintrag = f"{ergebnis.strip()}{zusatz}"
                                
                                # NEU: Das Training dauerhaft in die Cloud-Historie speichern!
                                if "gym_history" not in st.session_state.physio_data:
                                    st.session_state.physio_data["gym_history"] = []
                                st.session_state.physio_data["gym_history"].append(eintrag)
                                
                            except: pass
                            
                    save_all_to_supabase() 
                    st.success("✅ Erfasst! Bild und Anmerkung wurden für die KI verarbeitet und gespeichert.")
                    time.sleep(2)
                    st.rerun()
                
        st.write("---")
        
        # NEU: Die manuelle Eingabemaske zum Aufklappen
        with st.expander("✍️ Manuelle Aktivität hinzufügen (ohne Bild)"):
                with st.form("manual_gym_form", clear_on_submit=True):
                    c_datum, c_sport = st.columns(2)
                    # Nimmt als Standardwert automatisch das heutige Datum
                    with c_datum: m_datum = st.text_input("Datum (z.B. 18.06.2026)", value=datetime.now().strftime("%d.%m.%Y"))
                    with c_sport: m_sport = st.selectbox("Sportart / Aktivität", ["Krafttraining", "Yoga / Mobility", "Schwimmen", "Wandern", "Ski / Wintersport", "Alltag / Sonstiges"])
                    
                    c_dauer, c_kcal = st.columns(2)
                    with c_dauer: m_dauer = st.text_input("Dauer (z.B. 45 Min)")
                    with c_kcal: m_kcal = st.text_input("Kalorien (optional)")
                    
                    m_notiz = st.text_input("Notiz / Details (z.B. 'Fokus auf Beine und Core')")
                    
                    if st.form_submit_button("Aktivität speichern"):
                        # Textbausteine clever zusammensetzen
                        kcal_text = f" (*{m_kcal} kcal*)" if m_kcal else ""
                        dauer_text = f", {m_dauer}" if m_dauer else ""
                        notiz_text = f" - {m_notiz}" if m_notiz else ""
                        
                        neuer_eintrag = f"**{m_datum}** | {m_sport}{dauer_text}{notiz_text}{kcal_text}"
                        
                        # In die dauerhafte Cloud-Historie schieben
                        if "gym_history" not in st.session_state.physio_data:
                            st.session_state.physio_data["gym_history"] = []
                        st.session_state.physio_data["gym_history"].append(neuer_eintrag)
                        
                        save_all_to_supabase()
                        st.success("✅ Manuelle Aktivität gespeichert!")
                        time.sleep(1)
                        st.rerun()
    
        with st.expander("🤖 Workout-Analyse & Coach-Feedback"):
                with st.form("workout_analysis_form"):
                    analysis_upload = st.file_uploader("Screenshot der Trainingseinheit hochladen", type=["png", "jpg", "jpeg"], key="analysis_upload")
                    submit_analysis = st.form_submit_button("Workout tiefenanalysieren")
                    
                    if submit_analysis and analysis_upload:
                        img = Image.open(analysis_upload)
                        with st.spinner("Coach analysiert deine Übungen..."):
                            
                            # HIER KOMMT DEIN NEUER CODE HIN:
                            aktueller_plan = st.session_state.get('wochenplan', 'Kein Wochenplan vorhanden.')
                            ziel_kontext = st.session_state.physio_data.get('ziel_typ', 'Allgemeines Training')
                            
                            feedback_prompt = f"""Du bist ein erfahrener Fitness-Coach. Analysiere den Screenshot dieser Trainingseinheit und setze sie zwingend in Bezug zu meinem aktuellen Trainingsplan.
                            
                            Mein übergeordnetes Ziel: {ziel_kontext}
                            Mein aktueller Wochenplan:
                            {aktueller_plan}
                            
                            1. Erkenne die Sportart (Kraft, Ausdauer etc.) und bewerte die Metriken.
                            2. Beurteile konkret: Wie gut passt diese Einheit in meinen aktuellen Wochenplan? War sie für das Ziel zu hart, zu leicht oder genau richtig?
                            3. Gib ein kurzes, prägnantes Feedback (max. 4 Sätze) und einen Tipp, worauf ich bei den nächsten Einheiten des Plans achten sollte."""
                            
                            try:
                                feedback = ask_gemini_with_retry(client, feedback_prompt, [img])
                                st.markdown("### 📋 Dein Coach-Feedback:")
                                st.info(feedback)
                            except Exception as e:
                                st.error(f"Fehler bei der Analyse: {e}")

    # --- ANSICHT: EINSTELLUNGEN ---
    elif st.session_state.ansicht == "Einstellungen":
        st.header("⚙️ Setup: Ziele & Instruktionen")
        
        st.subheader("🎯 Dein Hauptziel")
        ziel_optionen = ["Spezielles Wettkampf-Event", "Formaufbau", "Formerhalt"]
        aktuelles_ziel = st.session_state.physio_data.get("ziel_typ", "Formaufbau")
        index_ziel = ziel_optionen.index(aktuelles_ziel) if aktuelles_ziel in ziel_optionen else 1
        
        # NEU: Selectbox (Dropdown) statt Radio-Buttons
        new_ziel_typ = st.selectbox("Was ist dein aktueller Fokus?", ziel_optionen, index=index_ziel)
        
        new_event_name = st.session_state.physio_data.get("event_name", "")
        new_event_datum = st.session_state.physio_data.get("event_datum", "")
        new_distanz = st.session_state.physio_data.get("distanz", "")
        new_zielzeit = st.session_state.physio_data.get("zielzeit", "")
        
        if new_ziel_typ == "Spezielles Wettkampf-Event":
            st.markdown("Bitte gib die Details für dein Event ein:")
            c_e, c_d, c_di, c_z = st.columns(4)
            with c_e: new_event_name = st.text_input("Event-Name", value=new_event_name)
            with c_d: new_event_datum = st.text_input("Datum", value=new_event_datum)
            with c_di: new_distanz = st.text_input("Distanz", value=new_distanz)
            with c_z: new_zielzeit = st.text_input("Zielzeit", value=new_zielzeit)
       
        st.subheader("⚖️ Körperdaten (Für exakte Berechnungen)")
        c_g, c_w = st.columns(2)
        with c_g: new_groesse = st.text_input("Körpergröße (cm)", value=st.session_state.physio_data.get("groesse", ""))
        with c_w: new_gewicht = st.text_input("Gewicht (kg)", value=st.session_state.physio_data.get("gewicht", ""))
        st.subheader("👨‍🏫 Spezifische Trainerinstruktionen")
        new_inst = st.text_area("Hier kannst du der KI besondere Vorlieben, Einschränkungen oder Trainingstage mitteilen:", 
                                value=st.session_state.physio_data.get("instructions", ""), height=150)
        
        st.write("---")
        if st.button("💾 Setup & Instruktionen in der Cloud speichern", type="primary"):
            st.session_state.physio_data.update({
                "ziel_typ": new_ziel_typ,
                "event_name": new_event_name,
                "event_datum": new_event_datum,
                "distanz": new_distanz,
                "zielzeit": new_zielzeit,
                "groesse": new_groesse,
                "gewicht": new_gewicht,
                "instructions": new_inst
            })
            if save_all_to_supabase():
                st.success("Erfolgreich in Supabase für dein Profil gespeichert!")
        
        # HIER REFORMIERT: Liegt nun außerhalb des Buttons, bleibt dauerhaft sichtbar
        st.subheader("📄 Hintergrundwissen & Trainingspläne")
        plan_uploads = st.file_uploader("Lade bis zu 5 Dokumente hoch (Pläne, PDFs, Bilder)", accept_multiple_files=True, type=["png", "jpg", "jpeg", "pdf"])

        if plan_uploads:
            if len(plan_uploads) > 5: st.warning("Nur die ersten 5 Dateien werden genutzt.")
            st.session_state.plan_images = []
            st.session_state.doc_texts = []
            
            for f in plan_uploads[:5]:
                if f.type == "application/pdf":
                    try:
                        reader = PyPDF2.PdfReader(f)
                        text = "".join([page.extract_text() for page in reader.pages])
                        st.session_state.doc_texts.append(text)
                    except: pass
                else:
                    st.session_state.plan_images.append(Image.open(f))
            st.success(f"✅ {len(plan_uploads[:5])} Datei(en) im Hintergrund gemerkt!")

    # --- ANSICHT: STATISTIKEN & PROGNOSEN ---
    elif st.session_state.ansicht == "Statistiken":
        st.header("📊 Deine Lauf-Prognose (8-Wochen-Trend)")
        st.info("Die App analysiert hier deine stärksten Paces und deine langen Läufe der letzten 8 Wochen, um deine echte Form zu berechnen.")
        st.info("Um eine realistische Prognose zu erhalten, stelle sicher, dass du in den letzten 8 Wochen mind. ein bis zwei intensive Einheiten oder einen Testlauf absolviert hast.")

        if st.session_state.strava_context:
            try:
                # 1. Daten aus Strava-Kontext extrahieren & filtern (nur Läufe, letzte 8 Wochen)
                acht_wochen_her = datetime.now() - timedelta(weeks=8)
                all_paces = [] # Pace in s/km
                long_runs_count = 0
                max_dist = 0
                
                for line in st.session_state.strava_context.split("\n"):
                    if "[Run]" in line or "[Lauf]" in line:
                        try:
                            date_str = line.split("] [")[0].replace("- [", "")
                            act_date = datetime.strptime(date_str, "%Y-%m-%d")
                            
                            if act_date >= acht_wochen_her:
                                dist = float(line.split(": ")[1].split(" km")[0])
                                max_dist = max(max_dist, dist)
                                
                                if "Pace: " in line:
                                    pace_str = line.split("Pace: ")[1].split(" min/km")[0]
                                    m, s = map(int, pace_str.split("."))
                                    pace_in_seconds = (m * 60) + s
                                    
                                    if pace_in_seconds > 180 and dist > 3: # Schneller als 3:00, länger als 3km
                                        all_paces.append(pace_in_seconds)
                                        if dist >= 15:
                                            long_runs_count += 1
                        except: continue

                # 2. Prognose berechnen
                if all_paces:
                    all_paces.sort()
                    top_x = max(1, int(len(all_paces) * 0.2)) # Die besten 20%
                    basis_pace_s = sum(all_paces[:top_x]) / top_x
                    
                    riegel_slope = 1.07 
                    endurance_bonus = min(0.05, long_runs_count * 0.006) 
                    
                    def get_slope_for_dist(target_dist):
                        experience_factor = 0
                        if max_dist < (target_dist * 0.5): experience_factor = 0.02
                        elif max_dist >= (target_dist * 0.9): experience_factor = -0.01 
                        return riegel_slope - endurance_bonus + experience_factor

                    slope_5 = get_slope_for_dist(5)
                    prog_5k_s = basis_pace_s * 5 * (5**0.03) 
                    
                    slope_10 = get_slope_for_dist(10)
                    prog_10k_s = prog_5k_s * (10/5)**slope_10
                    
                    slope_21 = get_slope_for_dist(21.1)
                    prog_21k_s = prog_5k_s * (21.1/5)**slope_21
                    
                    def fmt_s(s):
                        m, s = divmod(int(s), 60)
                        h, m = divmod(m, 60)
                        return f"{h:d}:{m:02d}:{s:02d}" if h > 0 else f"{m:d}:{s:02d}"

                    # 3. UI Darstellung
                    c_info, c_5k, c_10k, c_hm = st.columns([2,1,1,1])
                    with c_info:
                        # Vorbereitung als reine, sichere Textstücke
                        b_txt = fmt_s(basis_pace_s) + " min/km"
                        l_txt = str(long_runs_count)
                        m_txt = "{:.1f} km".format(max_dist)
                        
                        # Absolut sichere Verkettung ohne Zeilenumbrüche im String
                        html = "<div style='background-color: #f0f2f6; padding: 10px; border-radius: 5px; border-left: 5px solid #ff4b4b;'>"
                        html += "<small>Basis (Top 20% Pace):</small><br><b>" + b_txt + "</b><br>"
                        html += "<small>Lange Läufe (>15km, 8w): <b>" + l_txt + "</b></small><br>"
                        html += "<small>Längster Lauf (8w): <b>" + m_txt + "</b></small>"
                        html += "</div>"
                        
                        st.markdown(html, unsafe_allow_html=True)
                        # Hier werden die Werte sicher injiziert
                        st.markdown(html_template.format(basis_text, lange_laeufe_text, max_dist_text), unsafe_allow_html=True)
                    with c_5k: st.metric("5 km", fmt_s(prog_5k_s))
                    with c_10k: st.metric("10 km", fmt_s(prog_10k_s))
                    with c_hm: st.metric("Halbmarathon", fmt_s(prog_21k_s))

                else:
                    st.warning("Keine validen Läufe in den letzten 8 Wochen für eine Prognose gefunden.")
                    st.info("💡 **So löst du das:**\n"
                            "* **Daten abrufen:** Gehe in den Reiter **'Wochenplan'** und klicke auf den Button **'🔄 Wochenplan & Status aktualisieren'**. Das zieht die neuesten Daten von Strava in den App-Speicher.\n"
                            "* **Distanz:** Für eine sinnvolle Prognose wertet die App nur Läufe über **3 km** Distanz aus.\n"
                            "* **Realismus:** Um eine realistische Prognose zu erhalten, stelle sicher, dass du in den letzten 8 Wochen mindestens ein bis zwei intensive Einheiten oder einen Testlauf absolviert hast.")
            except Exception as e:
                st.error(f"Fehler bei der Prognose: {e}")
        else:
            st.info("Konnte keine Strava-Daten finden. Lade im Wochenplan einmal neu!")
    # ==============================================================================
    # 💬 CHAT-INTERFAZ (COACH TALK)
    # ==============================================================================
    st.divider()
    st.subheader("💬 Chat mit Coach")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if user_input := st.chat_input("Frage zum Plan..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"): st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Coach überlegt..."):
                try:
                    chat_prompt = f"""{zeit_befehl}
                    WICHTIGE REGELN FÜR DEN CHAT:
                    1. Beantworte die Frage als Coach kurz und empathisch.
                    2. Wenn der Nutzer möchte, dass du das Training anpasst (z. B. Einheiten verschieben, hinzufügen, streichen), schreibe den KOMPLETTEN neuen Wochenplan zwingend zwischen die Tags ===WOCHENPLAN_START=== und ===WOCHENPLAN_END===.
                    3. Schreibe außerhalb dieser Tags nur deine kurze Antwort für den Chat.
                    
                    Aktueller Plan:\n{st.session_state.get('wochenplan')}
                    Ziel:\n{ziel_kontext}
                    Frage: {user_input}"""
                    
                    resp = ask_gemini_with_retry(client, chat_prompt)
                    
                    # FILTER-LOGIK: Fische den Plan aus der Antwort heraus
                    if "===WOCHENPLAN_START===" in resp and "===WOCHENPLAN_END===" in resp:
                        neuer_plan = resp.split("===WOCHENPLAN_START===")[1].split("===WOCHENPLAN_END===")[0].strip()
                        
                        # Speichere den neuen Plan direkt in die Datenbank und den Session State!
                        save_all_to_supabase(woche_text=neuer_plan)
                        
                        # Schneide den Plan aus der angezeigten Chat-Nachricht heraus
                        plan_block = "===WOCHENPLAN_START===" + resp.split("===WOCHENPLAN_START===")[1].split("===WOCHENPLAN_END===")[0] + "===WOCHENPLAN_END==="
                        chat_antwort = resp.replace(plan_block, "").strip()
                        
                        # Falls die KI nur den Plan ohne Text geschickt hat:
                        if not chat_antwort:
                            chat_antwort = "✅ Ich habe deinen Wochenplan im Hintergrund aktualisiert. Schau gerne im Reiter 'Wochenplan' nach!"
                    else:
                        # Wenn kein Plan geändert wurde, zeige einfach den normalen Text
                        chat_antwort = resp.strip()

                    st.markdown(chat_antwort)
                    st.session_state.messages.append({"role": "assistant", "content": chat_antwort})
                except Exception as e: 
                    st.error(f"Server-Fehler. Bitte später noch einmal probieren. Fehler: {e}")
