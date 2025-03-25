import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import re
import datetime
import sys
import concurrent.futures
import os
import PyPDF2
import openai
import time
import json
import pdfplumber
import io

from typing import Dict, Any, Optional
from dotenv import load_dotenv
from PIL import Image
from scholarly import scholarly

from modules.online_api_filter import module_online_api_filter

# For translation if needed
from google_trans_new import google_translator

# ------------------------------------------------------------------
# Load environment variables (for OPENAI_API_KEY, if present)
# ------------------------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ------------------------------------------------------------------
# Streamlit configuration
# ------------------------------------------------------------------
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

# ------------------------------------------------------------------
# Login functionality
# ------------------------------------------------------------------
def login():
    st.title("Login")
    user_input = st.text_input("Username")
    pass_input = st.text_input("Password", type="password")
    
    if st.button("Login"):
        if (
            user_input == st.secrets["login"]["username"]
            and pass_input == st.secrets["login"]["password"]
        ):
            st.session_state["logged_in"] = True
        else:
            st.error("Login failed. Please check your credentials!")

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login()
    st.stop()

# ------------------------------------------------------------------
# 1) Common functions & classes
# ------------------------------------------------------------------

def clean_html_except_br(text):
    """Remove all HTML tags except <br>."""
    return re.sub(r'</?(?!br\b)[^>]*>', '', text)

def translate_text_openai(text, source_language, target_language, api_key):
    """Uses OpenAI ChatCompletion to translate text."""
    import openai
    openai.api_key = api_key
    prompt_system = (
        f"You are a translation engine from {source_language} to {target_language} for a biotech company called Novogenia "
        f"that focuses on lifestyle and health genetics and health analyses. The outputs you provide will be used directly as "
        f"the translated text blocks. Please translate as accurately as possible in the context of health and lifestyle reporting. "
        f"If there is no appropriate translation, the output should be 'TBD'. Keep the TAGS and do not add additional punctuation."
    )
    prompt_user = f"Translate the following text from {source_language} to {target_language}:\n'{text}'"
    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            temperature=0
        )
        translation = response.choices[0].message.content.strip()
        # strip quotes if present
        if translation and translation[0] in ["'", '"', "‘", "„"]:
            translation = translation[1:]
            if translation and translation[-1] in ["'", '"']:
                translation = translation[:-1]
        translation = clean_html_except_br(translation)
        return translation
    except Exception as e:
        st.warning(f"Translation Error: {e}")
        return text

# ------------------------------------------------------------------
# ... Other code / classes for searching in CORE, PubMed, etc. omitted for brevity ...
# ------------------------------------------------------------------

def page_home():
    st.title("Welcome to the Main Menu")
    st.write("Choose a module in the sidebar to proceed.")
    st.image("Bild1.jpg", caption="Welcome!", use_container_width=False, width=600)

def page_codewords_pubmed():
    st.title("Codewords & PubMed Settings")
    from modules.codewords_pubmed import module_codewords_pubmed
    module_codewords_pubmed()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_excel_online_search():
    st.title("Excel Online Search")
    from modules.online_api_filter import module_online_api_filter

def page_online_api_filter():
    st.title("Online-API_Filter (Combined)")
    st.write("Here you can combine API selection and online filter in one step.")
    module_online_api_filter()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

class PaperAnalyzer:
    """A class that extracts text from PDFs and sends it to OpenAI for analysis."""
    def __init__(self, model="gpt-3.5-turbo"):
        self.model = model

    def extract_text_from_pdf(self, pdf_file):
        """Extract plain text via PyPDF2 (if the PDF is searchable)."""
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text

    def analyze_with_openai(self, text, prompt_template, api_key):
        """Generic helper to call OpenAI with a given prompt template."""
        if len(text) > 15000:
            text = text[:15000] + "..."
        prompt = prompt_template.format(text=text)
        openai.api_key = api_key
        response = openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": (
                    "You are an expert in analyzing scientific papers, especially Side-Channel Analysis."
                )},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        return response.choices[0].message.content

    def summarize(self, text, api_key):
        """Generate a structured summary in German, up to 500 words."""
        prompt = (
            "Erstelle eine strukturierte Zusammenfassung des folgenden "
            "wissenschaftlichen Papers. Gliedere sie in mindestens vier klar getrennte Abschnitte "
            "(z.B. 1. Hintergrund, 2. Methodik, 3. Ergebnisse, 4. Schlussfolgerungen). "
            "Verwende maximal 500 Wörter:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def extract_key_findings(self, text, api_key):
        """Extract the 5 most important findings (German)."""
        prompt = (
            "Extrahiere die 5 wichtigsten Erkenntnisse aus diesem wissenschaftlichen Paper "
            "im Bereich Side-Channel Analysis. Liste sie mit Bulletpoints auf:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def identify_methods(self, text, api_key):
        """Identify the methods and techniques (German)."""
        prompt = (
            "Identifiziere und beschreibe die im Paper verwendeten Methoden "
            "und Techniken zur Side-Channel-Analyse. Gib zu jeder Methode "
            "eine kurze Erklärung:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def evaluate_relevance(self, text, topic, api_key):
        """Evaluate relevance on a scale of 1-10 (German)."""
        prompt = (
            f"Bewerte die Relevanz dieses Papers für das Thema '{topic}' auf "
            f"einer Skala von 1-10. Begründe deine Bewertung:\n\n{{text}}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

def page_analyze_paper():
    st.title("Analyze Paper - Integrated")

    if "api_key" not in st.session_state:
        st.session_state["api_key"] = OPENAI_API_KEY or ""

    # Reset / Start a new Analysis Button
    if st.button("Reset / Start a new Analysis"):
        if "analysis_results" in st.session_state:
            del st.session_state["analysis_results"]
        st.experimental_rerun()

    st.sidebar.header("Settings - PaperAnalyzer")
    new_key_value = st.sidebar.text_input("OpenAI API Key", type="password", value=st.session_state["api_key"])
    st.session_state["api_key"] = new_key_value

    model = st.sidebar.selectbox(
        "OpenAI Model",
        ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o"],
        index=0
    )

    # Analysis type
    action = st.sidebar.radio(
        "Analysis Type",
        [
            "Zusammenfassung",
            "Wichtigste Erkenntnisse",
            "Methoden & Techniken",
            "Relevanz-Bewertung",
            "Tabellen & Grafiken"
        ],
        index=0
    )

    # Language dropdown for final result
    output_lang = st.sidebar.selectbox(
        "Output Language for Analysis",
        ["Deutsch", "Englisch", "Portugiesisch", "Serbisch"],
        index=0
    )

    # Topic for Relevanz-Bewertung
    topic = st.sidebar.text_input("Topic (for Relevanz-Bewertung)?")

    # Combine multiple PDFs into one text?
    combine_texts_single_analysis = st.sidebar.checkbox("Combine selected PDFs into one single text?")

    uploaded_files = st.file_uploader("Upload PDF files", type="pdf", accept_multiple_files=True)
    analyzer = PaperAnalyzer(model=model)
    api_key = st.session_state["api_key"]

    if uploaded_files and api_key:
        st.write("## Single or Combined Analysis (No Excel)")
        if st.button("Start Analysis (No Excel)"):
            if combine_texts_single_analysis:
                # Combine all PDFs into one text
                combined_text = ""
                for pdf_file in uploaded_files:
                    extracted_text = analyzer.extract_text_from_pdf(pdf_file)
                    if extracted_text.strip():
                        combined_text += f"\n=== {pdf_file.name} ===\n{extracted_text}\n"
                    else:
                        st.warning(f"No text extracted from {pdf_file.name}, skipping.")

                if not combined_text.strip():
                    st.error("No text to analyze from selected PDFs.")
                    return

                if action == "Zusammenfassung":
                    r_ = analyzer.summarize(combined_text, api_key)
                elif action == "Wichtigste Erkenntnisse":
                    r_ = analyzer.extract_key_findings(combined_text, api_key)
                elif action == "Methoden & Techniken":
                    r_ = analyzer.identify_methods(combined_text, api_key)
                elif action == "Relevanz-Bewertung":
                    if not topic:
                        st.error("Please provide a topic for Relevanz-Bewertung!")
                        return
                    r_ = analyzer.evaluate_relevance(combined_text, topic, api_key)
                elif action == "Tabellen & Grafiken":
                    # disclaim partial table analysis
                    r_ = "(Partial table/graphic analysis in combined mode - not fully supported.)"
                else:
                    r_ = "(No analysis type selected.)"

                # Translate if needed
                if output_lang != "Deutsch":
                    lang_map = {
                        "Englisch": "English",
                        "Portugiesisch": "Portuguese",
                        "Serbisch": "Serbian"
                    }
                    target_lang = lang_map.get(output_lang, "English")
                    r_ = translate_text_openai(r_, "German", target_lang, api_key)

                st.subheader("Combined Analysis Result")
                st.write(r_)

            else:
                # Individual analysis
                final_results = []
                for pdf_file in uploaded_files:
                    extracted_text = analyzer.extract_text_from_pdf(pdf_file)
                    if not extracted_text.strip():
                        st.warning(f"No text extracted from {pdf_file.name}, skipping.")
                        continue

                    if action == "Zusammenfassung":
                        r_ = analyzer.summarize(extracted_text, api_key)
                    elif action == "Wichtigste Erkenntnisse":
                        r_ = analyzer.extract_key_findings(extracted_text, api_key)
                    elif action == "Methoden & Techniken":
                        r_ = analyzer.identify_methods(extracted_text, api_key)
                    elif action == "Relevanz-Bewertung":
                        if not topic:
                            st.error("Please provide a topic for Relevanz-Bewertung!")
                            continue
                        r_ = analyzer.evaluate_relevance(extracted_text, topic, api_key)
                    elif action == "Tabellen & Grafiken":
                        # minimal table parse with pdfplumber
                        table_lines = []
                        try:
                            with pdfplumber.open(pdf_file) as pdf_:
                                for pgnum, page in enumerate(pdf_.pages, start=1):
                                    found_tables = page.extract_tables()
                                    if found_tables:
                                        for tix, tdata in enumerate(found_tables, start=1):
                                            table_lines.append(
                                                f"Page {pgnum}, Table {tix}, row_count={len(tdata)}"
                                            )
                            if table_lines:
                                r_ = "Tables found:\n" + "\n".join(table_lines)
                            else:
                                r_ = "No tables found."
                        except Exception as e_:
                            r_ = f"Error reading tables: {e_}"
                    else:
                        r_ = "(No analysis type selected.)"

                    # Translate final result if needed
                    if output_lang != "Deutsch":
                        lang_map = {
                            "Englisch": "English",
                            "Portugiesisch": "Portuguese",
                            "Serbisch": "Serbian"
                        }
                        target_lang = lang_map.get(output_lang, "English")
                        r_ = translate_text_openai(r_, "German", target_lang, api_key)

                    final_results.append(f"**Result for {pdf_file.name}:**\n\n{r_}")

                st.subheader("Individual Analysis Results (No Excel)")
                st.markdown("\n\n---\n\n".join(final_results))
    else:
        if not api_key:
            st.warning("Please enter an OpenAI API key!")
        elif not uploaded_files:
            st.info("Please upload one or more PDF files!")

def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")
    pages = {
        "Home": page_home,
        "Online-API_Filter": page_online_api_filter,
        "3) Codewords & PubMed": page_codewords_pubmed,
        "Analyze Paper": page_analyze_paper,
    }
    for label, page_fn in pages.items():
        if st.sidebar.button(label, key=label):
            st.session_state["current_page"] = label

    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"

    return pages.get(st.session_state["current_page"], page_home)

def answer_chat(question: str) -> str:
    """Simple chat example with possible paper_text context."""
    api_key = st.session_state.get("api_key", "")
    paper_text = st.session_state.get("paper_text", "")
    if not api_key:
        return f"(No API-Key) Echo: {question}"

    if not paper_text.strip():
        sys_msg = "You are a helpful assistant for general questions."
    else:
        sys_msg = (
            "You are a helpful assistant, and here is a paper as context:\n\n"
            + paper_text[:12000] + "\n\n"
            "Use it to provide an expert answer."
        )

    openai.api_key = api_key
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": question}
            ],
            temperature=0.3,
            max_tokens=400
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"OpenAI error: {e}"

def main():
    st.markdown(
        """
        <style>
        html, body {
            margin: 0;
            padding: 0;
        }
        .scrollable-chat {
            max-height: 400px;
            overflow-y: scroll;
            border: 1px solid #CCC;
            padding: 8px;
            margin-top: 10px;
            border-radius: 4px;
            background-color: #f9f9f9;
        }
        .message {
            padding: 0.5rem 1rem;
            border-radius: 15px;
            margin-bottom: 0.5rem;
            max-width: 80%;
            word-wrap: break-word;
        }
        .user-message {
            background-color: #e3f2fd;
            margin-left: auto;
            border-bottom-right-radius: 0;
        }
        .assistant-message {
            background-color: #f0f0f0;
            margin-right: auto;
            border-bottom-left-radius: 0;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    col_left, col_right = st.columns([4, 1])
    with col_left:
        page_fn = sidebar_module_navigation()
        if page_fn is not None:
            page_fn()

    with col_right:
        st.subheader("Chatbot")

        if "chat_history" not in st.session_state:
            st.session_state["chat_history"] = []

        user_input = st.text_input("Your question here", key="chatbot_right_input")
        if st.button("Send (Chat)", key="chatbot_right_send"):
            if user_input.strip():
                st.session_state["chat_history"].append(("user", user_input))
                bot_answer = answer_chat(user_input)
                st.session_state["chat_history"].append(("bot", bot_answer))

        st.markdown('<div class="scrollable-chat" id="chat-container">', unsafe_allow_html=True)
        for role, msg_text in st.session_state["chat_history"]:
            if role == "user":
                st.markdown(
                    f'<div class="message user-message"><strong>You:</strong> {msg_text}</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div class="message assistant-message"><strong>Bot:</strong> {msg_text}</div>',
                    unsafe_allow_html=True
                )
        st.markdown('</div>', unsafe_allow_html=True)

        # Auto-scroll script
        st.markdown(
            """
            <script>
                function scrollToBottom() {
                    var container = document.getElementById('chat-container');
                    if(container) {
                        container.scrollTop = container.scrollHeight;
                    }
                }
                document.addEventListener('DOMContentLoaded', function() {
                    scrollToBottom();
                });
                const observer = new MutationObserver(function(mutations) {
                    scrollToBottom();
                });
                setTimeout(function() {
                    var container = document.getElementById('chat-container');
                    if(container) {
                        observer.observe(container, { childList: true });
                        scrollToBottom();
                    }
                }, 1000);
            </script>
            """,
            unsafe_allow_html=True
        )

if __name__ == '__main__':
    main()
