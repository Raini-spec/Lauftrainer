col_btn1, col_btn2 = st.columns(2)
            
            with col_btn1:
                if st.button("⚡ Nur Leistungsstatus aktualisieren", use_container_width=True):
                    st.session_state.run_status_update = True
            with col_btn2:
                if st.button("🔄 Kompletten Wochenplan anpassen", type="primary", use_container_width=True):
                    st.session_state.run_update = True

            # ==============================================================================
            # LOGIK 1: NUR LEISTUNGSSTATUS AKTUALISIEREN
            # ==============================================================================
            if st.session_state.get("run_status_update"):
                if load_and_format_strava_data():
                    try:
                        with st.spinner("Berechne Leistungsstatus..."):
                            prompt_status = f"""
                            {zeit_befehl}
                            Berechne AUSSCHLIESSLICH den neuen Leistungszustand basierend auf meinen Strava-Daten.
                            VO2MAX-REGEL: Der letzte berechnete VO2max war {aktueller_vo2max}. Passe ihn maximal um +/- 0.5 Punkte an.
                            
                            Strava-Historie:\n{st.session_state.strava_context}
                            
                            Gib AUSSCHLIESSLICH das JSON-Format aus:
                            ===STATUS_START===
                            {{"vo2max": "Zahl", "prognose_5k": "Zeit", "prognose_10k": "Zeit", "prognose_21k": "Zeit", "belastung": "Kurzer Text", "belastung_prozent": "Zahl 0-100"}}
                            ===STATUS_END===
                            """
                            
                            with st.expander("🔍 KI-Inspektor: Gesendeter Status-Prompt"):
                                st.code(prompt_status)
                                
                            text = ask_gemini_with_retry(client, prompt_status, st.session_state.doc_images)
                            status_part = text.split("===STATUS_START===")[1].split("===STATUS_END===")[0].strip() if "===STATUS_START===" in text else "{}"
                            
                            s_json = json.loads(status_part) if "vo2max" in status_part else {}
                            s_json["letztes_update"] = datetime.now().strftime("%d.%m.%Y")
                            
                            save_all_to_supabase(status_json=s_json)
                            st.session_state.run_status_update = False
                            st.rerun()
                    except Exception as e:
                        st.error(f"Fehler: {e}")
                        st.session_state.run_status_update = False

            # ==============================================================================
            # LOGIK 2: KOMPLETTEN WOCHENPLAN ANPASSEN
            # ==============================================================================
            if st.session_state.get("run_update"):
                if load_and_format_strava_data():
                    try:
                        with st.spinner("Berechne adaptiven Wochenplan und speichere in Cloud..."):
                            prompt = f"""
                            {zeit_befehl}
                            
                            🚨 STRIKTE DATEN- & LOGIK-REGELN:
                            1. DATUMS-REGEL: Die Strava-Daten sind HISTORIE! Wenn es in dieser Woche bereits vergangene Tage gibt, trage die dort absolvierten Trainings aus den Strava-Daten exakt als "✅ Bereits absolviert" in Woche 1 ein.
                            2. VALIDIERUNG: Vergleiche jeden Tag im Masterplan mit meinen Strava-Aktivitäten. Markiere als "✅ Bereits absolviert" NUR Tage, an denen ich laut Strava-Daten TATSÄCHLICH trainiert habe. Wenn für einen geplanten Tag KEINE Strava-Aktivität vorliegt, markiere ihn keinesfalls als absolviert!
                            3. ADAPTION: Wenn ich laut Plan ein Training hatte, aber in Strava nichts dazu steht, markiere es als "❌ Ausgefallen / Nicht absolviert" und schlage eine Anpassung vor.
                            4. BELASTUNGS-LOGIK: Wenn ich am Di/Mi hart gelaufen bin, ist das Training für morgen (Do) zu streichen oder durch aktive Erholung zu ersetzen. Analysiere meine Belastung der letzten 48h vor jeder Planung!
                            
                            Masterplan:\n{st.session_state.trainingsplan}
                            Strava-Historie:\n{st.session_state.strava_context}
                            Ziel & Event:\n{ziel_kontext}
                            Instruktionen:\n{trainer_instructions}
                            
                            AUFGABE: 
                            1. LÄNGE DES PLANS: Du darfst EXAKT NUR ZWEI WOCHEN ausgeben (Woche 1 und Woche 2). Es ist dir strengstens verboten, Woche 3 oder spätere Wochen zu generieren. Schneide alles danach rigoros ab!
                            2. Extrahiere die heutige und morgige Einheit.
                            3. Berechne den Leistungszustand.
                            VO2MAX-REGEL: Der letzte berechnete VO2max war {aktueller_vo2max}. Passe ihn basierend auf den neuen Strava-Daten maximal um +/- 0.5 Punkte an.
                            {output_format_alle}
                            """
                            
                            with st.expander("🔍 KI-Inspektor: Gesendeter Wochenplan-Prompt"):
                                st.code(prompt)
                                
                            text = ask_gemini_with_retry(client, prompt, st.session_state.doc_images)
                            
                            status_part = text.split("===STATUS_START===")[1].split("===STATUS_END===")[0].strip() if "===STATUS_START===" in text else "{}"
                            h_part = text.split("===HEUTE_START===")[1].split("===HEUTE_END===")[0].strip() if "===HEUTE_START===" in text else ""
                            m_part = text.split("===MORGEN_START===")[1].split("===MORGEN_END===")[0].strip() if "===MORGEN_START===" in text else ""
                            w_part = text.split("===WOCHENPLAN_START===")[1].split("===WOCHENPLAN_END===")[0].strip() if "===WOCHENPLAN_START===" in text else ""
                            w_json_part = text.split("===WEEK_JSON_START===")[1].split("===WEEK_JSON_END===")[0].strip() if "===WEEK_JSON_START===" in text else "[]"
                            st.session_state.wochenplan_json = w_json_part
                            
                            s_json = json.loads(status_part) if "vo2max" in status_part else {}
                            s_json["letztes_update"] = datetime.now().strftime("%d.%m.%Y")
                            
                            save_all_to_supabase(woche_text=w_part, status_json=s_json, heute_text=h_part, morgen_text=m_part)
                            
                            st.session_state.run_update = False
                            st.rerun()
                    except Exception as e: 
                        st.error(f"Fehler bei KI-Verarbeitung: {e}")
                        st.session_state.run_update = False
                else: 
                    st.error("Konnte Strava-Daten nicht laden.")
                    st.session_state.run_update = False
