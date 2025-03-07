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

# ----------------- Debug-Informationen (für Fehlersuche) -------------------
st.sidebar.markdown("**[DEBUG-INFO]**")
st.sidebar.code(f"""
Aktuelles Arbeitsverzeichnis: {os.getcwd()}
Systempfad (sys.path): {sys.path}
""")

# --------------------------------------------------------------------------
# A) Pfad für lokales PaperQA (wenn Sie es in modules/paper-qa/paperqa nutzen)
# --------------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Wichtig: KEIN doppeltes "modules"!
# Wir gehen davon aus, dass es so liegt: modules/paper-qa/paperqa/__init__.py
PAPERQA_LOCAL_PATH = os.path.join(CURRENT_DIR, "modules", "paper-qa", "paperqa")

if not os.path.exists(PAPERQA_LOCAL_PATH):
    st.error(f"Kritischer Pfadfehler: {PAPERQA_LOCAL_PATH} existiert nicht!")
    st.stop()

# Diesen Ordner in den Python-Pfad aufnehmen, falls noch nicht vorhanden
if PAPERQA_LOCAL_PATH not in sys.path:
    sys.path.insert(0, PAPERQA_LOCAL_PATH)

# Versuch, PaperQA zu importieren
try:
    from paperqa import Docs
except ImportError as e:
    st.error(
        "Konnte 'paperqa' nicht importieren. "
        "Bitte prüfe, ob im Ordner 'paper-qa/paperqa' eine Datei '__init__.py' liegt "
        "und ob Du die Struktur korrekt hast.\n"
        f"Aktueller Pfad: {PAPERQA_LOCAL_PATH}\nFehler:\n{e}"
    )
    st.stop()

# --------------------------------------------------------------------------
# Eventuell weitere Bibliotheken
# --------------------------------------------------------------------------
try:
    from scholarly import scholarly
except ImportError:
    st.error("Bitte installiere 'scholarly' (z.B. mit 'pip install scholarly').")

import openai
try:
    from fpdf import FPDF
except ImportError:
    st.error("Bitte installiere 'fpdf' (z.B. mit 'pip install fpdf').")


# --------------------------------------------------------------------------
# Globale Profil-Verwaltung in st.session_state
# --------------------------------------------------------------------------
def load_settings(profile_name: str):
    """
    Lädt ein bestehendes Profil aus st.session_state['profiles'] und aktualisiert die Session-Werte.
    """
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
    """
    Speichert alle relevanten Einstellungen und Listen in st.session_state['profiles'][profile_name].
    """
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
# ChatGPT: Paper erstellen & lokal speichern
# --------------------------------------------------------------------------
def generate_paper_via_chatgpt(prompt_text, model="gpt-3.5-turbo"):
    try:
        openai.api_key = st.secrets["OPENAI_API_KEY"]
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=1200,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(
            f"Fehler bei ChatGPT-API-Aufruf: '{e}'.\n"
            "Prüfe, ob 'OPENAI_API_KEY' in secrets.toml hinterlegt ist!"
        )
        return ""

def save_text_as_pdf(text, pdf_path, title="ChatGPT-Paper"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, title, ln=1)
    pdf.ln(5)

    lines = text.split("\n")
    for line in lines:
        pdf.multi_cell(0, 8, line)
        pdf.ln(2)

    pdf.output(pdf_path, "F")


# --------------------------------------------------------------------------
# arXiv-Suche & Download
# --------------------------------------------------------------------------
def search_arxiv_papers(query, max_results=5):
    base_url = "http://export.arxiv.org/api/query?"
    params = {"search_query": f"all:{query}", "start": 0, "max_results": max_results}
    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
    except Exception as e:
        st.error(f"Fehler beim Abrufen von arXiv: {e}")
        return []
    
    feed = feedparser.parse(response.text)
    papers_info = []
    for entry in feed.entries:
        title = entry.title
        summary = entry.summary
        link_pdf = None
        for link in entry.links:
            if link.rel == "related" and "pdf" in link.type:
                link_pdf = link.href
                break
            elif link.type == "application/pdf":
                link_pdf = link.href
                break
        papers_info.append({
            "title": title,
            "summary": summary,
            "pdf_url": link_pdf
        })
    return papers_info

def sanitize_filename(fname):
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", fname)

def download_arxiv_pdf(pdf_url, local_filepath):
    try:
        r = requests.get(pdf_url, timeout=15)
        r.raise_for_status()
        with open(local_filepath, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        st.error(f"Fehler beim Herunterladen der PDF: {e}")
        return False


# --------------------------------------------------------------------------
# Beispiel: Lokaler PaperQA-Test mit Docs()
# --------------------------------------------------------------------------
def paperqa_test():
    st.subheader("Lokaler PaperQA-Test (Docs-Klasse)")
    st.write("Hier kannst du PDFs hochladen und anschließend Fragen stellen (lokale PaperQA).")

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
# Haupt-Menü
# --------------------------------------------------------------------------
def main():
    st.set_page_config(layout="wide")
    st.title("Kombinierte App: ChatGPT, arXiv-Suche, PaperQA (lokal)")

    # Standard-Werte in Session anlegen
    if "profiles" not in st.session_state:
        st.session_state["profiles"] = {}
    if "selected_genes" not in st.session_state:
        st.session_state["selected_genes"] = []
    if "synonyms_selected" not in st.session_state:
        st.session_state["synonyms_selected"] = {}
    if "codewords_str" not in st.session_state:
        st.session_state["codewords_str"] = ""
    if "final_gene" not in st.session_state:
        st.session_state["final_gene"] = ""

    # Standard-Flags
    if "use_pubmed" not in st.session_state:
        st.session_state["use_pubmed"] = True
    if "use_epmc" not in st.session_state:
        st.session_state["use_epmc"] = True
    if "use_google" not in st.session_state:
        st.session_state["use_google"] = False
    if "use_semantic" not in st.session_state:
        st.session_state["use_semantic"] = False
    if "use_openalex" not in st.session_state:
        st.session_state["use_openalex"] = False
    if "use_core" not in st.session_state:
        st.session_state["use_core"] = False
    if "use_chatgpt" not in st.session_state:
        st.session_state["use_chatgpt"] = False

    menu = [
        "Home / Profile",
        "ChatGPT-Paper",
        "arXiv-Suche",
        "PaperQA-Test"
    ]
    choice = st.sidebar.selectbox("Navigation", menu)

    # 1) Profilverwaltung
    if choice == "Home / Profile":
        st.subheader("Profilverwaltung / Übersicht")
        colp1, colp2 = st.columns([2,1])

        with colp1:
            profile_name_input = st.text_input("Profilname (zum Speichern):", "")
            if st.button("Profil speichern"):
                if profile_name_input.strip():
                    save_current_settings(profile_name_input.strip())
                else:
                    st.warning("Bitte einen Profilnamen eingeben.")

        with colp2:
            profiles_existing = list(st.session_state["profiles"].keys())
            prof_sel = st.selectbox("Profil laden:", ["(kein)"] + profiles_existing)
            if st.button("Profil übernehmen"):
                if prof_sel != "(kein)":
                    loaded = load_settings(prof_sel)
                    if loaded:
                        st.success(f"Profil '{prof_sel}' geladen.")
                else:
                    st.info("Kein Profil ausgewählt.")

        st.write("**Aktuelle Session-Einstellungen:**")
        st.json({
            "selected_genes":       st.session_state["selected_genes"],
            "synonyms_selected":    st.session_state["synonyms_selected"],
            "codewords_str":        st.session_state["codewords_str"],
            "final_gene":           st.session_state["final_gene"],
            "use_pubmed":           st.session_state["use_pubmed"],
            "use_epmc":             st.session_state["use_epmc"],
            "use_google":           st.session_state["use_google"],
            "use_semantic":         st.session_state["use_semantic"],
            "use_openalex":         st.session_state["use_openalex"],
            "use_core":             st.session_state["use_core"],
            "use_chatgpt":          st.session_state["use_chatgpt"],
        })

    # 2) ChatGPT-Paper generieren
    elif choice == "ChatGPT-Paper":
        st.subheader("1) Paper mit ChatGPT generieren & lokal speichern")
        prompt_txt = st.text_area("Prompt:", "Schreibe ein Paper über KI in der Medizin.")
        local_dir = st.text_input("Zielordner lokal:", "chatgpt_papers")
        if st.button("Paper generieren"):
            text = generate_paper_via_chatgpt(prompt_txt)
            if text:
                if not os.path.exists(local_dir):
                    os.makedirs(local_dir, exist_ok=True)
                time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                pdf_name = f"chatgpt_paper_{time_str}.pdf"
                pdf_path = os.path.join(local_dir, pdf_name)
                save_text_as_pdf(text, pdf_path, title="ChatGPT-Paper")
                st.success(f"Paper gespeichert unter: {pdf_path}")

    # 3) arXiv-Suche & PDF-Download
    elif choice == "arXiv-Suche":
        st.subheader("2) arXiv-Suche & PDF-Download (lokal)")
        query = st.text_input("arXiv Suchbegriff:", "quantum computing")
        num = st.number_input("Anzahl", 1, 50, 5)
        local_dir_arxiv = st.text_input("Ordner für Downloads:", "arxiv_papers")

        if st.button("arXiv-Suche starten"):
            results = search_arxiv_papers(query, max_results=num)
            if not results:
                st.info("Keine Treffer.")
            else:
                st.write(f"Treffer: {len(results)}")
                if not os.path.exists(local_dir_arxiv):
                    os.makedirs(local_dir_arxiv, exist_ok=True)
                for i, paper in enumerate(results, start=1):
                    st.write(f"**{i})** {paper['title']}")
                    st.write(paper['summary'][:300], "...")
                    if paper["pdf_url"]:
                        fname = sanitize_filename(paper["title"][:50]) + ".pdf"
                        path_ = os.path.join(local_dir_arxiv, fname)
                        if st.button(f"PDF herunterladen: {fname}", key=f"arxiv_{i}"):
                            ok_ = download_arxiv_pdf(paper["pdf_url"], path_)
                            if ok_:
                                st.success(f"PDF gespeichert: {path_}")
                    else:
                        st.write("_Kein PDF-Link._")
                    st.write("---")

    # 4) Lokaler PaperQA-Test
    else:
        paperqa_test()


if __name__ == "__main__":
    main()
