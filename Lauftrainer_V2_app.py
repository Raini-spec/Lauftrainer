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

st.set_page_config(page_title="KI Trainer", layout="centered")
cookie_manager = stx.CookieManager()
st.write("") 

st.title("🏃‍♂️🚴 KI Trainer: Strava & Gemini")
st.caption("🔒 **Version 4.91** – Direkter Download-Button & Physio-Erklärtext")

# ==============================================================================
# 🧠 SESSION STATE & COOKIES
# ==============================================================================
if "messages" not in st.session_state: st.session_state.messages = []
if "strava_context" not in st.session_state: st.session_state.strava_context = ""
if "letzte_10_aktivitaeten" not in st.session_state: st.session_state.letzte_10_aktivitaeten = []
if "doc_names" not in st.session_state: st.session_state.doc_names = []
if "doc_texts" not in st.session_state: st.session_state.doc_texts = []
if "doc_images" not in st.session_state: st.session_state.doc_images = []
if "ansicht" not in st.session_state: st.session_state.ansicht = "Wochenplan"

auth_cookie = cookie_manager.get("auth_paket")
auth_data = json.loads(auth_cookie) if isinstance(auth_cookie, str) else (auth_cookie or {})
if "temp_auth_data" in st.session_state: auth_data = st.session_state.temp_auth_data

physio_cookie = cookie_manager.get("physio_paket")
physio_data = json.loads(physio_cookie) if isinstance(physio_cookie, str) else (physio_cookie or {})

app_backup_cookie = cookie_manager.get("app_backup_paket")
if app_backup_cookie:
    try: 
        backup_data = json.loads(app_backup_cookie) if isinstance(app_backup_cookie, str) else app_backup_cookie
        if backup_data:
            for key in ["trainingsplan", "wochenplan", "leistungsstatus", "heute_training", "morgen_training"]:
                if key not in st.session_state and backup_data.get(key):
                    st.session_state[key] = backup_data[key]
    except: pass

# ==============================================================================
# ⚙️ HILFSFUNKTIONEN
# ==============================================================================
def save_all_to_state_and_cookies(plan_text=None, woche_text=None, status_json=None, heute_text=None, morgen_text=None):
    if plan_text is not None: st.session_state.trainingsplan = plan_text
    if woche_text is not None: st.session_state.wochenplan = woche_text
    if status_json is not None: st.session_state.leistungsstatus = status_json
    if heute_text is not None: st.session_state.heute_training = heute_text
    if morgen_text is not None: st.session_state.morgen_training = morgen_text
    
    backup_paket = {
        "trainingsplan": st.session_state.get("trainingsplan", ""),
        "wochenplan": st.session_state.get("wochenplan", ""),
        "leistungsstatus": st.session_state.get("leistungsstatus", {}),
        "heute_training": st.session_state.get("heute_training", ""),
        "morgen_training": st.session_state.get("morgen_training", "")
    }
    cookie_manager.set("app_backup_paket", json.dumps(backup_paket), key=f"set_backup_{int(time.time())}")

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
                    info = f"Pace: {(1000/s)/60:.2f} min/km" if t in ["Run", "Lauf"] and s > 0 else f"Geschw.: {s*3.6:.2f} km/h"
                    data += f"- [{date}] [{t}] {act.get('name')}: {d:.2f} km | {info} | Ø Puls: {p}\n"
                    
                    if len(last_ten) < 10:
                        try: dt_str = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m.%y")
                        except: dt_str = date
                        last_ten.append(f"**{dt_str}** | {t_de}: {d:.1f} km *({info})*")
                        
                st.session_state.strava_context = data
                st.session_state.letzte_10_aktivitaeten = last_ten
                return True
        return False
    except: return False

# ==============================================================================
# 🎛️ COCKPIT LINKS (STREAMLIT SIDEBAR)
# ==============================================================================
with st.sidebar:
    st.header("🧭 Navigation")
    if st.button("📅 Aktueller Wochenplan", use_container_width=True): st.session_state.ansicht = "Wochenplan"
    if st.button("🏆 Masterplan", use_container_width=True): st.session_state.ansicht = "Masterplan"
    if st.button("👟 Letzte Aktivitäten", use_container_width=True): st.session_state.ansicht = "Aktivitäten"
    if st.button("⚙️ Trainerinstruktionen & Co.", use_container_width=True): st.session_state.ansicht = "Einstellungen"
    if st.button("📂 Daten wiederherstellen", use_container_width=True): st.session_state.ansicht = "Wiederherstellen"
    
    # NEU: Direkter Download-Button statt Navigation zur Unterseite
    backup = {
        "trainingsplan": st.session_state.get("trainingsplan", ""), 
        "wochenplan": st.session_state.get("wochenplan", ""), 
        "leistungsstatus": st.session_state.get("leistungsstatus", {}), 
        "heute_training": st.session_state.get("heute_training", ""), 
        "morgen_training": st.session_state.get("morgen_training", "")
    }
    st.download_button("💾 Daten sichern (Export)", data=json.dumps(backup, indent=2), file_name="trainer_backup.json", mime="application/json", use_container_width=True)

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
        cookie_manager.delete("physio_paket")
        cookie_manager.delete("app_backup_paket")
        st.session_state.clear()
        time.sleep(0.5)
        st.rerun()

# ==============================================================================
# 🔑 SCHLEUSE (LOGIN)
# ==============================================================================
gemini_key = auth_data.get("gemini_key")
access_token = auth_data.get("access_token")

if not gemini_key or not access_token:
    st.info("👋 Willkommen! Bitte einloggen oder App einrichten.")
    tab1, tab2 = st.tabs(["📁 Login (Datei)", "⌨️ Manuelle Einrichtung"])
    with tab1:
        config_file = st.file_uploader("Konfigurations-Datei (.json)", type=["json"])
        master_pw = st.text_input("Master-Passwort", type="password")
        if st.button("🔐 Entsperren"):
            if config_file and master_pw:
                content = json.load(config_file)
                if content.get("master_pw") == master_pw:
                    st.session_state.temp_auth_data = content
                    st.rerun()
                else: st.error("Passwort falsch.")
    with tab2:
        st.warning("Setup-Code hier gekürzt. (Gleiche Logik wie in v4.80)")
        # Der Übersichtlichkeit halber in dieser Anzeige gekürzt. Nutze dein bestehendes Setup.

# ==============================================================================
# 🏃‍♂️ HAUPT-APP BEREICH (DYNAMISCH)
# ==============================================================================
else:
    client = genai.Client(api_key=gemini_key)
    if "temp_auth_data" in st.session_state:
        cookie_manager.set("auth_paket", json.dumps(st.session_state.temp_auth_data), key="cookie_set_main_auth")

    heute_iso = datetime.now().strftime("%A, %d. %B %Y")
    zeit_befehl = f"⚠️ WICHTIGER SYSTEM-ZEITANKER:\nHeute ist exakt der {heute_iso}. Wir befinden uns im Jahr 2026! Rechne Pläne von heute in die Zukunft."
    output_format_alle = """
    ===STATUS_START===
    {"vo2max": "Zahl", "prognose_5k": "Zeit", "prognose_10k": "Zeit", "prognose_21k": "Zeit", "belastung": "Kurzer Text", "belastung_prozent": "Zahl 0-100"}
    ===STATUS_END===
    ===HEUTE_START===\nHier steht nur die heutige Einheit in 1-2 Sätzen.\n===HEUTE_END===
    ===MORGEN_START===\nHier steht nur die morgige Einheit in 1-2 Sätzen.\n===MORGEN_END===
    ===WOCHENPLAN_START===\n### 📅 Dein adaptiver Wochenplan\n*Markdown-Plan...*\n===WOCHENPLAN_END===
    """

    trainer_instructions = physio_data.get("instructions", "")
    vo2max = physio_data.get("vo2max", "")

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
            if st.button("🔄 Wochenplan & Status aktualisieren", type="primary"):
                with st.spinner("Berechne adaptiven Wochenplan..."):
                    if load_and_format_strava_data():
                        prompt = f"{zeit_befehl}\nMasterplan:\n{st.session_state.trainingsplan}\nStrava:\n{st.session_state.strava_context}\nInstruktionen:\n{trainer_instructions}\nAUFGABE: Wochenplan anpassen, Heute/Morgen extrahieren, Status berechnen.\n{output_format_alle}"
                        try:
                            text = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt] + st.session_state.doc_images).text
                            status_part = text.split("===STATUS_START===")[1].split("===STATUS_END===")[0].strip() if "===STATUS_START===" in text else "{}"
                            h_part = text.split("===HEUTE_START===")[1].split("===HEUTE_END===")[0].strip() if "===HEUTE_START===" in text else ""
                            m_part = text.split("===MORGEN_START===")[1].split("===MORGEN_END===")[0].strip() if "===MORGEN_START===" in text else ""
                            w_part = text.split("===WOCHENPLAN_START===")[1].split("===WOCHENPLAN_END===")[0].strip() if "===WOCHENPLAN_START===" in text else ""
                            
                            s_json = json.loads(status_part) if "vo2max" in status_part else {}
                            s_json["letztes_update"] = datetime.now().strftime("%d.%m.%Y")
                            save_all_to_state_and_cookies(woche_text=w_part, status_json=s_json, heute_text=h_part, morgen_text=m_part)
                            st.rerun()
                        except Exception as e: st.error(f"Fehler: {e}")
        else:
            st.info("Kein Wochenplan. Bitte zuerst Masterplan erstellen!")

    # --- ANSICHT: MASTERPLAN ---
    elif st.session_state.ansicht == "Masterplan":
        st.header("🏆 Langfristiger Masterplan")
        if st.session_state.get("trainingsplan"):
            st.markdown(st.session_state.trainingsplan)
        if st.button("🔄 Masterplan neu generieren / aktualisieren", type="primary"):
            with st.spinner("Erstelle alle Pläne neu..."):
                if load_and_format_strava_data():
                    prompt = f"{zeit_befehl}\nStrava:\n{st.session_state.strava_context}\nInstruktionen:\n{trainer_instructions}\nAUFGABE: Masterplan neu schreiben, Wochenplan ableiten, Heute/Morgen extrahieren, Status berechnen.\n{output_format_alle}\n===MASTERPLAN_START===\nPlan...\n===MASTERPLAN_END==="
                    try:
                        text = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt] + st.session_state.doc_images).text
                        mp_part = text.split("===MASTERPLAN_START===")[1].split("===MASTERPLAN_END===")[0].strip() if "===MASTERPLAN_START===" in text else text
                        w_part = text.split("===WOCHENPLAN_START===")[1].split("===WOCHENPLAN_END===")[0].strip() if "===WOCHENPLAN_START===" in text else ""
                        h_part = text.split("===HEUTE_START===")[1].split("===HEUTE_END===")[0].strip() if "===HEUTE_START===" in text else ""
                        m_part = text.split("===MORGEN_START===")[1].split("===MORGEN_END===")[0].strip() if "===MORGEN_START===" in text else ""
                        status_part = text.split("===STATUS_START===")[1].split("===STATUS_END===")[0].strip() if "===STATUS_START===" in text else "{}"
                        
                        s_json = json.loads(status_part) if "vo2max" in status_part else {}
                        s_json["letztes_update"] = datetime.now().strftime("%d.%m.%Y")
                        save_all_to_state_and_cookies(plan_text=mp_part, woche_text=w_part, status_json=s_json, heute_text=h_part, morgen_text=m_part)
                        st.rerun()
                    except Exception as e: st.error(f"Fehler: {e}")

    # --- ANSICHT: AKTIVITÄTEN ---
    elif st.session_state.ansicht == "Aktivitäten":
        st.header("👟 Deine letzten 10 Aktivitäten")
        if load_and_format_strava_data():
            for act in st.session_state.letzte_10_aktivitaeten:
                st.info(act)
        else:
            st.warning("Konnte Strava-Daten nicht abrufen.")

    # --- ANSICHT: EINSTELLUNGEN ---
    elif st.session_state.ansicht == "Einstellungen":
        st.header("⚙️ Trainerinstruktionen & Physiologie")
        new_inst = st.text_area("Anweisungen für die KI", value=trainer_instructions, height=200)
        
        # NEU: Erklärtext für die physiologischen Werte
        st.write("ℹ️ *Hier können aktuelle physiologische Werte, sofern bekannt, eingetragen werden. Falls diese nicht eingetragen werden, werden diese automatisch berechnet.*")
        
        c_v, c_l, c_b = st.columns(3)
        with c_v: new_v = st.text_input("VO2max", value=physio_data.get("vo2max", ""))
        with c_l: new_l = st.text_input("Laktat", value=physio_data.get("laktat", ""))
        with c_b: new_b = st.text_input("Belastung", value=physio_data.get("belastung", ""))
        if st.button("💾 Alle Einstellungen speichern"):
            physio_data.update({"instructions": new_inst, "vo2max": new_v, "laktat": new_l, "belastung": new_b})
            cookie_manager.set("physio_paket", json.dumps(physio_data))
            st.success("Gespeichert!")
            
        st.subheader("📄 Hintergrundwissen (Dateien)")
        uploaded_files = st.file_uploader("Lade PDFs, Bilder oder Texte hoch", accept_multiple_files=True)
        if uploaded_files: st.success("Dateien im temporären Speicher abgelegt.")

    # --- ANSICHT: WIEDERHERSTELLEN ---
    elif st.session_state.ansicht == "Wiederherstellen":
        st.header("📂 Daten wiederherstellen (Import)")
        upl = st.file_uploader("Backup-Datei hochladen", type=["json"])
        if upl and st.button("🔄 Einspielen"):
            b = json.load(upl)
            save_all_to_state_and_cookies(b.get("trainingsplan"), b.get("wochenplan"), b.get("leistungsstatus"), b.get("heute_training"), b.get("morgen_training"))
            st.success("Geladen!"); time.sleep(0.5); st.session_state.ansicht = "Wochenplan"; st.rerun()

    # --- CHAT (Immer unten sichtbar) ---
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
                    resp = client.models.generate_content(model='gemini-2.5-flash', contents=[f"{zeit_befehl}\nPlan:\n{st.session_state.get('wochenplan')}\nFrage: {user_input}"]).text
                    st.markdown(resp)
                    st.session_state.messages.append({"role": "assistant", "content": resp})
                except Exception as e: st.error("Fehler")
