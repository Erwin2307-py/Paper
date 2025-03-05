import streamlit as st
import requests
import feedparser
import pandas as pd
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
try:
    from scholarly import scholarly
except ImportError:
    st.error("Bitte installiere 'scholarly', z.B. via: pip install scholarly")

import openai
try:
    from fpdf import FPDF
except ImportError:
    st.error("Bitte installiere 'fpdf', z.B. mit: pip install fpdf")


###############################################################################
# Hilfsfunktionen (gekürzte Version; nur wichtige Teile)
###############################################################################

def generate_paper_via_chatgpt(prompt_text, model="gpt-3.5-turbo"):
    """Ruft die ChatGPT-API auf und erzeugt ein Paper (Text)."""
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
        st.error(f"Fehler bei ChatGPT-API: {e}")
        return ""

def save_text_as_pdf(text, pdf_path, title="Paper"):
    """Speichert den gegebenen Text in ein PDF (lokal)."""
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

def search_pubmed(query: str, max_results=100):
    """Sehr gekürzt: Sucht auf PubMed."""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max_results
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        pmids = data.get("esearchresult", {}).get("idlist", [])
        return pmids
    except Exception as e:
        st.error(f"PubMed-Suche fehlgeschlagen: {e}")
        return []

def search_google_scholar(query: str, max_results=100):
    results = []
    try:
        for idx, pub in enumerate(scholarly.search_pubs(query)):
            if idx >= max_results:
                break
            bib = pub.get("bib", {})
            results.append({"title": bib.get("title","n/a")})
        return results
    except Exception as e:
        st.error(f"Google Scholar-Suche fehlgeschlagen: {e}")
        return []

def load_settings(profile_name: str):
    if "profiles" in st.session_state:
        return st.session_state["profiles"].get(profile_name, None)
    return None

###############################################################################
# ChatGPT-Scoring
###############################################################################
def chatgpt_online_search_with_genes(papers, codewords, genes, top_k=100):
    """
    Beispiel: ChatGPT soll alle Paper scoren (0-100), 
    wobei wir Codewords + Gene übergeben. 
    Wenn Codewords = "", ignoriert ChatGPT die Codewörter de facto.
    """
    if not papers:
        return []

    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        st.error("Kein 'OPENAI_API_KEY' in st.secrets! Abbruch.")
        return []

    results_scored = []
    genes_str = ", ".join(genes) if genes else ""
    code_str = codewords if codewords else ""

    for paper in papers:
        title = paper.get('title', '(kein Titel)')
        prompt_text = (
            f"Codewörter: {code_str}\n"
            f"Gene: {genes_str}\n\n"
            f"Paper:\n"
            f"Titel: {title}\n"
            "Gib mir eine Zahl von 0 bis 100 (Relevanz)."
        )
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=20,
                temperature=0
            )
            raw_text = response.choices[0].message.content.strip()
            match = re.search(r'(\d+)', raw_text)
            score = int(match.group(1)) if match else 0
        except Exception as e:
            st.error(f"Fehler bei ChatGPT-Scoring: {e}")
            score = 0

        new_p = dict(paper)
        new_p["Relevance"] = score
        results_scored.append(new_p)

    # Sort nach Relevanz
    results_scored.sort(key=lambda x: x["Relevance"], reverse=True)
    return results_scored[:top_k]


###############################################################################
# Multi-API-Suche (mit Checkbox "Nur nach Gen suchen?")
###############################################################################
def module_codewords_pubmed():
    st.title("Multi-API-Suche: Genes + Codewords (Optional)")

    # Profile-Check
    if "profiles" not in st.session_state or not st.session_state["profiles"]:
        st.warning("Keine Profile hinterlegt.")
        return

    # Profil auswählen
    prof_names = list(st.session_state["profiles"].keys())
    chosen_profile = st.selectbox("Profil:", ["(kein)"] + prof_names)
    if chosen_profile == "(kein)":
        st.info("Kein Profil gewählt -> Abbruch.")
        return

    profile_data = load_settings(chosen_profile)
    if not profile_data:
        st.warning("Profil nicht gefunden?")
        return
    
    st.write("Profil-Daten:", profile_data)

    # Aus dem Profil:
    default_codewords = profile_data.get("codewords", "")
    genes_from_profile = profile_data.get("genes", [])

    # Checkbox: Nur nach Gen suchen?
    only_gene_box = st.checkbox("Nur nach Gen(s) suchen?", value=False)

    codewords_str = st.text_input("Codewörter", value=default_codewords)
    st.write(f"Genes aus Profil: {genes_from_profile}")

    # Logik wählbar
    logic_option = st.radio("Logik (für Codewords + Genes):", ["OR", "AND"], index=0)

    if st.button("Suche starten"):
        # 1) Falls die Checkbox aktiv ist, ignorieren wir die Codewords
        if only_gene_box:
            codewords_str = ""

        # 2) Codewörter in Liste
        raw_words_list = [w.strip() for w in codewords_str.replace(",", " ").split() if w.strip()]
        # 3) Genes
        raw_genes_list = genes_from_profile

        if not raw_words_list and not raw_genes_list:
            st.warning("Weder Codewords noch Gene vorhanden -> Abbruch.")
            return

        # Query bauen
        if logic_option == "OR":
            query_codewords = " OR ".join(raw_words_list) if raw_words_list else ""
            query_genes = " OR ".join(raw_genes_list) if raw_genes_list else ""
            if query_codewords and query_genes:
                final_query = f"({query_codewords}) OR ({query_genes})"
            else:
                final_query = query_codewords or query_genes
        else:
            # AND
            query_codewords = " AND ".join(raw_words_list) if raw_words_list else ""
            query_genes = " AND ".join(raw_genes_list) if raw_genes_list else ""
            if query_codewords and query_genes:
                final_query = f"({query_codewords}) AND ({query_genes})"
            else:
                final_query = query_codewords or query_genes

        st.write("Finale Suchanfrage:", final_query)

        # Beispiel: 2 Such-APIs (PubMed und Google)
        pubmed_ids = []
        google_res = []

        if profile_data.get("use_pubmed", False):
            pubmed_ids = search_pubmed(final_query, max_results=10)
            st.write(f"PubMed: {len(pubmed_ids)} PMIDs gefunden")

        if profile_data.get("use_google", False):
            google_res = search_google_scholar(final_query, max_results=10)
            st.write(f"Google: {len(google_res)} Artikel gefunden")

        all_papers = []
        # Konstruieren wir Minimal-Infos:
        for pm in pubmed_ids:
            all_papers.append({"source":"PubMed", "title": f"PubMed PMID {pm}"})
        for gg in google_res:
            all_papers.append({"source":"Google Scholar", "title": gg.get("title","n/a")})

        if not all_papers:
            st.info("Keine Ergebnisse.")
            return

        st.session_state["search_results"] = all_papers
        st.write(f"{len(all_papers)} Ergebnisse gesamt.")

    # Falls Ergebnisse in Session
    if "search_results" in st.session_state and st.session_state["search_results"]:
        all_papers = st.session_state["search_results"]
        st.write(all_papers)

        st.write("---")
        st.subheader("ChatGPT-Online-Filterung (mit Gene & Codewords)")

        if st.button("Starte ChatGPT-Filterung"):
            # Falls die Checkbox „Nur nach Gen“ aktiv war, ignorieren wir Codewords
            final_codewords = ""
            if not only_gene_box: 
                # Dann Codewords normal nehmen
                final_codewords = codewords_str

            top_scored = chatgpt_online_search_with_genes(
                all_papers,
                codewords=final_codewords,
                genes=genes_from_profile,
                top_k=5
            )
            st.write("Top 5 Paper nach ChatGPT (Relevanz):")
            st.write(top_scored)


###############################################################################
# Hauptfunktion
###############################################################################
def main():
    st.title("Beispiel-App: Checkbox 'Nur nach Gen suchen?'")

    # Beispielhaftes Profil in die SessionState
    if "profiles" not in st.session_state:
        st.session_state["profiles"] = {
            "MeinProfil": {
                "use_pubmed": True,
                "use_google": True,
                "genes": ["BRCA1", "TP53"],
                "codewords": "cancer therapy"
            }
        }

    menu = ["ChatGPT-Paper", "Multi-API-Suche"]
    choice = st.sidebar.selectbox("Navigation", menu)

    if choice == "ChatGPT-Paper":
        st.subheader("Paper mit ChatGPT generieren & speichern")
        prompt_txt = st.text_area("Prompt eingeben:", "Schreibe ein kurzes Paper über KI in der Medizin.")
        if st.button("Generieren & Speichern"):
            txt = generate_paper_via_chatgpt(prompt_txt)
            if txt:
                fname = f"Paper_{int(time.time())}.pdf"
                save_text_as_pdf(txt, fname)
                st.success(f"PDF gespeichert: {fname}")
    else:
        st.subheader("Multi-API-Suche mit Checkbox 'Nur nach Gen suchen?'")
        module_codewords_pubmed()


if __name__ == "__main__":
    st.set_page_config(layout="wide")
    main()
