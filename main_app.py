import streamlit as st
import requests
import xml.etree.ElementTree as ET
import PyPDF2
import logging
import openai

from io import BytesIO
from PIL import Image
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import Chroma
from streamlit_feedback import streamlit_feedback

# Sicherstellen, dass OpenAI-API-Schlüssel gesetzt ist
api_key = None
if "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]
elif "OPENAI_API_KEY" in st.session_state:
    api_key = st.session_state["OPENAI_API_KEY"]

if api_key:
    openai.api_key = api_key
else:
    st.warning("⚠️ OpenAI API-Schlüssel nicht gesetzt. Bitte in den Streamlit Secrets oder als Umgebungsvariable hinzufügen.")

st.set_page_config(page_title="Multi-Modul Demo mit PaperQA2 & Chroma", layout="wide")

logging.basicConfig(level=logging.INFO)

################################################################################
# 1) PDF-Extraktion (nur digitale PDFs mit PyPDF2)
################################################################################

def extract_text_from_pdf(pdf_file) -> str:
    """
    Versucht, digitalen Text mit PyPDF2 auszulesen.
    Gibt einen String zurück (ggf. leer, wenn kein Text gefunden wurde).
    """
    text = ""
    try:
        reader = PyPDF2.PdfReader(pdf_file)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    except Exception as e:
        logging.error(f"Fehler beim Lesen mit PyPDF2: {e}")
    return text.strip()

################################################################################
# 2) Chroma + OpenAI Q&A
################################################################################

def create_vectorstore_from_text(text: str):
    """
    Teilt den Text in Chunks und erstellt eine Chroma-Datenbank
    mit OpenAI-Embeddings. Gibt das VectorStore-Objekt zurück.
    """
    text_splitter = CharacterTextSplitter(separator="\n", chunk_size=1000, chunk_overlap=100)
    chunks = text_splitter.split_text(text)
    logging.info(f"Text in {len(chunks)} Chunks aufgeteilt.")

    embeddings = OpenAIEmbeddings()
    vectorstore = Chroma.from_texts(chunks, embedding=embeddings)
    return vectorstore

def answer_question(query: str, vectorstore):
    """
    Sucht in der Vektordatenbank nach relevantem Kontext und
    erzeugt eine Antwort mit OpenAI ChatCompletion.
    """
    docs = vectorstore.similarity_search(query, k=4)
    logging.info(f"{len(docs)} relevante Textstellen für die Anfrage gefunden.")

    context = "\n".join([d.page_content for d in docs])
    system_message = {
        "role": "system",
        "content": (
            "You are a helpful research assistant. You answer questions based on the provided paper excerpts. "
            "If the context is insufficient, say you don't have enough information. Answer concisely and helpfully."
        )
    }
    user_message = {
        "role": "user",
        "content": f"Context:\n{context}\n\nQuestion: {query}"
    }

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[system_message, user_message],
            temperature=0.2,
        )
        answer = response["choices"][0]["message"]["content"].strip()
        return answer
    except Exception as e:
        logging.error(f"Fehler bei der OpenAI-Anfrage: {e}")
        return "Entschuldigung, es gab ein Problem bei der Beantwortung durch die KI."

################################################################################
# 3) PaperQA2 Modul
################################################################################

def module_paperqa2():
    st.title("🔎 PaperQA2 – Fragen zu wissenschaftlichen Papern")

    if "paper_text" not in st.session_state or not st.session_state["paper_text"]:
        st.warning("⚠️ Kein Paper geladen. Bitte zuerst ein PDF hochladen.")
        return

    st.write(f"Stellen Sie eine Frage zu **{st.session_state['paper_name']}**:")
    question = st.text_input("Ihre Frage", "")

    if st.button("Antwort generieren"):
        if not question.strip():
            st.error("Bitte geben Sie eine Frage ein.")
        else:
            with st.spinner("⏳ Die KI verarbeitet Ihre Frage..."):
                answer = answer_question(question, st.session_state["vectorstore"])
                st.success("✅ Antwort:")
                st.write(answer)

################################################################################
# 4) PaperQA Chroma Modul
################################################################################

def module_paperqa_chroma():
    st.title("🧠 PaperQA Chroma – Wissenschaftliche Paper analysieren")

    if "paper_text" not in st.session_state or not st.session_state["paper_text"]:
        st.warning("⚠️ Kein Paper geladen. Bitte zuerst ein PDF hochladen.")
        return

    st.write(f"Stellen Sie eine Frage zu **{st.session_state['paper_name']}** (Chroma-basiert):")
    question = st.text_input("Ihre Frage an Chroma", "")

    if st.button("Antwort generieren (Chroma)"):
        if not question.strip():
            st.error("Bitte geben Sie eine Frage ein.")
        else:
            with st.spinner("⏳ Chroma verarbeitet Ihre Frage..."):
                answer = answer_question(question, st.session_state["vectorstore"])
                st.success("✅ Antwort:")
                st.write(answer)

################################################################################
# 5) Haupt-App mit Navigation & Online-Suche
################################################################################

def main():
    st.title("📄 Multi-Modul Demo mit PaperQA2 & Chroma")
    st.write("Laden Sie ein PDF hoch und nutzen Sie PaperQA2 oder Chroma für Fragen.")

    uploaded_files = st.file_uploader("📄 PDF-Dokument hochladen", type=["pdf"], accept_multiple_files=True)
    if uploaded_files:
        all_text = ""
        for file in uploaded_files:
            file_text = extract_text_from_pdf(file)
            if file_text.strip():
                all_text += file_text + "\n"

        if all_text.strip():
            vectorstore = create_vectorstore_from_text(all_text)
            st.session_state["paper_text"] = all_text
            st.session_state["vectorstore"] = vectorstore
            st.session_state["paper_name"] = uploaded_files[0].name
            st.success("✅ PDF erfolgreich verarbeitet.")

    # Sidebar Navigation
    st.sidebar.title("🗂 Module")
    if st.sidebar.button("📑 PaperQA2 starten"):
        st.session_state["current_page"] = "paperqa2"
    if st.sidebar.button("🧠 PaperQA Chroma starten"):
        st.session_state["current_page"] = "paperqa_chroma"
    if st.sidebar.button("🔍 Online API-Suche starten"):
        st.session_state["current_page"] = "online_api_filter"
    if st.sidebar.button("⬅ Zurück zum Hauptmenü"):
        st.session_state["current_page"] = "home"

    # Navigation zwischen den Modulen
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "home"

    if st.session_state["current_page"] == "home":
        st.write("📌 Bitte laden Sie ein PDF hoch und wählen Sie ein Modul.")
    elif st.session_state["current_page"] == "paperqa2":
        module_paperqa2()
    elif st.session_state["current_page"] == "paperqa_chroma":
        module_paperqa_chroma()
    elif st.session_state["current_page"] == "online_api_filter":
        module_online_api_filter()

if __name__ == "__main__":
    main()
