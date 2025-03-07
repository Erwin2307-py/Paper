import streamlit as st
import requests
import feedparser
import pandas as pd
import os
import io
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict
import base64
import sys
import importlib.util  # <-- für dynamischen Import

# ----------------- Debug-Informationen (für Fehlersuche) -------------------
st.sidebar.markdown("**[DEBUG-INFO]**")
st.sidebar.code(f"""
Aktuelles Arbeitsverzeichnis: {os.getcwd()}
Systempfad (sys.path): {sys.path}
""")

# --------------------------------------------------------------------------
# A) Pfad zur __init__.py von PaperQA (DIREKT)
# --------------------------------------------------------------------------
# Beispiel: "Paper/modules/paper-qa/paperqa/__init__.py"
# Passen Sie ggf. an Ihre echte Struktur an. Hier ist es "Paper/modules/..."
PAPERQA_INIT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "Paper", "modules", "paper-qa", "paperqa", "__init__.py"
)

# Wir testen, ob die Datei existiert
if not os.path.isfile(PAPERQA_INIT_FILE):
    st.error(f"Kritischer Pfadfehler: {PAPERQA_INIT_FILE} existiert nicht!")
    st.stop()

# Dynamischer Import via importlib
# => Erzeugt ein (beliebig benanntes) Python-Modul-Objekt
try:
    spec = importlib.util.spec_from_file_location("paperqa_custom", PAPERQA_INIT_FILE)
    paperqa_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paperqa_module)
    # Nun haben wir "paperqa_module" als dynamisch geladenes Modul.
    # Falls in __init__.py "from .core import Docs" oder ähnliches importiert wird,
    # können wir direkt auf paperqa_module.Docs zugreifen.
    # Prüfen Sie, ob "Docs" dort ansprechbar ist:
    if not hasattr(paperqa_module, "Docs"):
        st.error("Im dynamisch geladenen 'paperqa_module' ist kein 'Docs' vorhanden!")
        st.stop()
except Exception as e:
    st.error(f"Fehler beim Import von PaperQA via {PAPERQA_INIT_FILE}: {e}")
    st.stop()

# -> Wir haben nun "paperqa_module" als Namespace, und dort sollte "Docs" liegen:
Docs = paperqa_module.Docs

# --------------------------------------------------------------------------
# Beispiel: Profilverwaltung (unverändert)
# --------------------------------------------------------------------------
def load_settings(profile_name: str):
    if "profiles" not in st.session_state:
        return None
    profile_data = st.session_state["profiles"].get(profile_name, None)
    if profile_data:
        st.session_state["selected_genes"]       = profile_data.get("selected_genes", [])
        st.session_state["synonyms_selected"]    = profile_data.get("synonyms_selected", {})
        st.session_state["codewords_str"]        = profile_data.get("codewords_str", "")
        st.session_state["final_gene"]           = profile_data.get("final_gene", "")
        st.session_state["use_pubmed"]           = profile_data.get("use_pubmed", True)
        st.session_state["use_epmc"]             = profile_data.get("use_epmc", True)
        st.session_state["use_google"]           = profile_data.get("use_google", False)
        st.session_state["use_semantic"]         = profile_data.get("use_semantic", False)
        st.session_state["use_openalex"]         = profile_data.get("use_openalex", False)
        st.session_state["use_core"]             = profile_data.get("use_core", False)
        st.session_state["use_chatgpt"]          = profile_data.get("use_chatgpt", False)
    return profile_data

def save_current_settings(profile_name: str):
    if "profiles" not in st.session_state:
        st.session_state["profiles"] = {}
    st.session_state["profiles"][profile_name] = {
        "selected_genes":     st.session_state.get("selected_genes", []),
        "synonyms_selected":  st.session_state.get("synonyms_selected", {}),
        "codewords_str":      st.session_state.get("codewords_str", ""),
        "final_gene":         st.session_state.get("final_gene", ""),
        "use_pubmed":         st.session_state.get("use_pubmed", True),
        "use_epmc":           st.session_state.get("use_epmc", True),
        "use_google":         st.session_state.get("use_google", False),
        "use_semantic":       st.session_state.get("use_semantic", False),
        "use_openalex":       st.session_state.get("use_openalex", False),
        "use_core":           st.session_state.get("use_core", False),
        "use_chatgpt":        st.session_state.get("use_chatgpt", False),
    }
    st.success(f"Profil '{profile_name}' erfolgreich gespeichert.")

# --------------------------------------------------------------------------
# B) PaperQA Test-Funktion
# --------------------------------------------------------------------------
def paperqa_test():
    st.subheader("Lokaler PaperQA-Test (dynamischer Import via init-Datei)")
    st.write("Hier kannst du PDFs hochladen und anschließend Fragen stellen.")

    # Wir greifen hier auf "Docs" aus dem dynamisch geladenen Modul zu
    docs = Docs()

    uploaded_files = st.file_uploader("PDFs hochladen", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        for up in uploaded_files:
            pdf_bytes = up.read()
            try:
                docs.add(pdf_bytes, metadata=up.name)
                st.success(f"{up.name} hinzugefügt.")
            except Exception as e:
                st.error(f"Fehler beim Einlesen {up.name}: {e}")

    question = st.text_input("Frage an die hochgeladenen PDFs:")
    if st.button("An PaperQA fragen"):
        if not question.strip():
            st.warning("Bitte eine Frage eingeben.")
        else:
            try:
                answer_obj = docs.query(question)
                st.markdown("### Antwort:")
                st.write(answer_obj.answer)
                with st.expander("Kontext / Belege"):
                    st.write(answer_obj.context)
            except Exception as e:
                st.error(f"Fehler bei PaperQA-Abfrage: {e}")

# --------------------------------------------------------------------------
# Haupt-Menü (Minimalbeispiel)
# --------------------------------------------------------------------------
def main():
    st.set_page_config(layout="wide")
    st.title("PaperQA via direktem Pfad zur __init__.py (Kein sys.path)")

    st.info("Dieses Skript importiert PaperQA, indem es direkt die Datei '__init__.py' lädt.")

    if st.button("PaperQA-Test starten"):
        paperqa_test()

if __name__ == "__main__":
    main()
