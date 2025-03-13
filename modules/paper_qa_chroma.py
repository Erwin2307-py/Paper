import streamlit as st
import PyPDF2
import pdfplumber
import pytesseract
import openai
import logging

from PIL import Image
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.embeddings import OpenAIEmbeddings  # Neuer Importpfad
from langchain_community.vectorstores import Chroma         # Neuer Importpfad
from streamlit_feedback import streamlit_feedback

logging.basicConfig(level=logging.INFO)

##############################################
# 1) PDF-Extraktion (nur digitale PDFs mit PyPDF2)
##############################################

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

##############################################
# 2) Chroma + OpenAI Q&A
##############################################

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
    erzeugt eine Antwort mit openai.ChatCompletion.
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
        answer = response.choices[0].message.content.strip()
        return answer
    except Exception as e:
        logging.error(f"Fehler bei der OpenAI-Anfrage: {e}")
        return "Entschuldigung, es gab ein Problem bei der Beantwortung durch die KI."

##############################################
# 3) Feedback
##############################################

def save_feedback(index):
    """
    Callback-Funktion für Feedback (Daumen hoch/runter).
    """
    feedback_value = st.session_state.get(f"feedback_{index}")
    st.session_state.history[index]["feedback"] = feedback_value
    logging.info(f"Feedback für Nachricht {index}: {feedback_value}")

##############################################
# 4) Haupt-App
##############################################

def main():
    st.title("📄 Paper-QA Chatbot (Nur digitale PDFs, Offizielle Chroma via langchain-community)")
    
    # Falls du deinen OpenAI-Key aus st.secrets nutzt:
    # openai.api_key = st.secrets["OPENAI_API_KEY"]

    uploaded_files = st.file_uploader(
        "PDF-Dokument(e) hochladen (nur digitale PDFs):",
        type=["pdf"],
        accept_multiple_files=True
    )

    if uploaded_files:
        all_text = ""
        for file in uploaded_files:
            file_text = extract_text_from_pdf(file)
            if file_text.strip():
                all_text += file_text + "\n"

        if all_text.strip():
            vectorstore = create_vectorstore_from_text(all_text)
            st.session_state.vectorstore = vectorstore
            st.success("Wissensdatenbank aus den hochgeladenen PDFs wurde erfolgreich erstellt!")
        else:
            st.error(
                "Es konnte kein Text aus den PDFs extrahiert werden.\n\n"
                "Mögliche Ursachen:\n"
                "- Das PDF enthält keinen maschinenlesbaren Text (z.B. gescannte Bilder).\n"
                "- Das PDF ist verschlüsselt oder geschützt.\n\n"
                "Bitte laden Sie nur digitale PDFs hoch."
            )

    # Chat-Verlauf initialisieren
    if "history" not in st.session_state:
        st.session_state.history = []

    # Bisherigen Chat-Verlauf anzeigen
    for i, msg in enumerate(st.session_state.history):
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant":
                feedback = msg.get("feedback")
                st.session_state[f"feedback_{i}"] = feedback
                streamlit_feedback(
                    feedback_type="thumbs",
                    key=f"feedback_{i}",
                    disabled=feedback is not None,
                    on_change=save_feedback,
                    args=(i,),
                )

    # Neue Chat-Eingabe
    if prompt := st.chat_input("Frage zu den hochgeladenen Papern stellen..."):
        with st.chat_message("user"):
            st.write(prompt)
        st.session_state.history.append({"role": "user", "content": prompt})

        if "vectorstore" not in st.session_state:
            st.error("Bitte lade mindestens ein PDF hoch, bevor du Fragen stellst.")
        else:
            answer = answer_question(prompt, st.session_state.vectorstore)
            with st.chat_message("assistant"):
                st.write(answer)
                streamlit_feedback(
                    feedback_type="thumbs",
                    key=f"feedback_{len(st.session_state.history)}",
                    on_change=save_feedback,
                    args=(len(st.session_state.history),),
                )
            st.session_state.history.append({"role": "assistant", "content": answer})

if __name__ == "__main__":
    main()
