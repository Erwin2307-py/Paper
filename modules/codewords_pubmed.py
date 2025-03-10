import streamlit as st
import requests
import feedparser
import pandas as pd
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict
import base64
import sys
import openai  # Updated OpenAI import

# ------------------------ Streamlit Cloud-Pfadkonfiguration ------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PAPERQA_PATH = os.path.join(CURRENT_DIR, "modules", "paper-qa")

# ------------------------ Systempfad & Package-Überprüfung ------------------------
def validate_environment():
    """Überprüft alle kritischen Abhängigkeiten und Pfade"""
    
    # 1. PaperQA-Pfad validieren
    required_files = [
        os.path.join(PAPERQA_PATH, "paperqa", "__init__.py"),
        os.path.join(PAPERQA_PATH, "setup.py")
    ]
    
    for file in required_files:
        if not os.path.exists(file):
            st.error(f"KRITISCHER FEHLER: Datei nicht gefunden - {file}")
            st.stop()

    # 2. Python-Pfad anpassen
    if PAPERQA_PATH not in sys.path:
        sys.path.insert(0, PAPERQA_PATH)

# ------------------------ OpenAI-Initialisierung ------------------------
def init_openai():
    """Konfiguriert die OpenAI-API"""
    if "OPENAI_API_KEY" not in st.secrets:
        st.error("OPENAI_API_KEY fehlt in Streamlit Secrets!")
        st.stop()
    
    openai.api_key = st.secrets["OPENAI_API_KEY"]
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]

# ------------------------ PaperQA-Import ------------------------
try:
    from paperqa import Docs
except ImportError as e:
    st.error(f"""
    PaperQA-Importfehler: {e}
    1. Repository als Submodule hinzufügen:
       git submodule add https://github.com/Future-House/paper-qa.git modules/paper-qa
    2. Submodule aktualisieren:
       git submodule update --init --recursive
    """)
    st.stop()

# ------------------------ Hauptfunktionen (aktualisiert) ------------------------
def paperqa_query_interface():
    """Aktualisierte PaperQA-Integration mit Fehlerhandling"""
    st.subheader("PaperQA Dokumentenanalyse")
    
    try:
        docs = Docs()
        uploaded_files = st.file_uploader(
            "PDF-Dokumente hochladen",
            type=["pdf"],
            accept_multiple_files=True
        )

        if uploaded_files:
            for file in uploaded_files:
                with st.spinner(f"Verarbeite {file.name}..."):
                    try:
                        docs.add(file.read(), metadata=file.name)
                        st.success(f"{file.name} erfolgreich analysiert")
                    except Exception as e:
                        st.error(f"Verarbeitungsfehler {file.name}: {str(e)}")

        question = st.text_area("Stellen Sie eine Frage zu den Dokumenten:")
        
        if st.button("Analyse starten") and question:
            with st.spinner("Analysiere Dokumente..."):
                try:
                    answer = docs.query(question)
                    display_paperqa_results(answer)
                except openai.AuthenticationError as e:
                    st.error(f"OpenAI Authentifizierungsfehler: {e}")
                except Exception as e:
                    st.error(f"Analysefehler: {str(e)}")

    except Exception as e:
        st.error(f"Initialisierungsfehler: {str(e)}")

def display_paperqa_results(answer):
    """Zeigt PaperQA-Ergebnisse mit erweitertem Format"""
    st.subheader("Analyseergebnisse")
    st.markdown(f"**Zusammenfassung:**\n{answer.answer}")
    
    with st.expander("🧪 Wissenschaftliche Belege"):
        for doc in answer.docs:
            st.markdown(f"""
            ### {doc.metadata.get('name', 'Unbekanntes Dokument')}
            **Relevanz-Score:** {doc.score:.2f}  
            **Auszug:**  
            {doc.text[:500]}...
            """)
    
    with st.expander("🔍 Vollständiger Kontext"):
        st.markdown(answer.context)

# ------------------------ Hauptprogramm ------------------------
def main():
    st.set_page_config(
        page_title="Wissenschaftliche Analyseplattform",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialisierung
    validate_environment()
    init_openai()
    
    # UI
    st.title("🔬 Wissenschaftliche Analyseplattform")
    paperqa_query_interface()

if __name__ == "__main__":
    main()
