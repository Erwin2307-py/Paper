import streamlit as st
import PyPDF2
import pdfplumber
import openai
import logging
import numpy as np
import easyocr

from PIL import Image
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings.openai import OpenAIEmbeddings  # Korrekt: aus dem "openai"-Modul
from langchain.vectorstores import FAISS  # Wir verwenden FAISS als Vektorstore
from streamlit_feedback import streamlit_feedback

logging.basicConfig(level=logging.INFO)

##############################################
# 1) PDF-Extraktion (PyPDF2 + OCR-Fallback mit EasyOCR)
##############################################

def extract_text_pypdf2(pdf_file) -> str:
    """Versucht, Text mit PyPDF2 auszulesen."""
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

def extract_text_easyocr(pdf_file) -> str:
    """
    Fallback-OCR mittels pdfplumber + EasyOCR.
    Wandelt jede Seite in ein Bild um und nutzt EasyOCR für die Texterkennung.
    """
    ocr_text = ""
    try:
        # Initialisiere den EasyOCR-Reader (Sprachliste anpassen, hier z.B. Deutsch)
        reader = easyocr.Reader(['de'], gpu=False)
        with pdfplumber.open(pdf_file) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                pil_img = page.to_image(resolution=200).original
                # Konvertiere das PIL-Bild in ein Numpy-Array
                img_array = np.array(pil_img)
                result = reader.readtext(img_array, detail=0)
                page_text = " ".join(result)
                if page_text.strip():
                    logging.debug(f"EasyOCR auf Seite {page_index}: {len(page_text.strip())} Zeichen erkannt.")
                    ocr_text += page_text + "\n"
                else:
                    logging.debug(f"EasyOCR auf Seite {page_index} lieferte keinen Text.")
    except Exception as e:
        logging.error(f"Fehler bei EasyOCR: {e}")
    return ocr_text.strip()

def extract_text_from_pdf(pdf_file) -> str:
    """
    1) Versuche, mit PyPDF2 digitalen Text auszulesen.
    2) Falls kein Text gefunden wird, OCR-Fallback mit pdfplumber + EasyOCR.
    """
    text_pypdf = extract_text_pypdf2(pdf_file)
    if text_pypdf:
        logging.info("Erfolgreich Text mit PyPDF2 extrahiert.")
        return text_pypdf

    logging.info("Kein Text via PyPDF2 gefunden. Versuche OCR-Fallback mit EasyOCR ...")
    text_easyocr = extract_text_easyocr(pdf_file)
    if text_easyocr:
        logging.info("OCR-Fallback war erfolgreich (EasyOCR).")
        return text_easyocr
    else:
        logging.warning("OCR-Fallback hat ebenfalls keinen Text gefunden.")
        return ""

##############################################
# 2) FAISS + OpenAI Q&A
##############################################

def create_vectorstore_from_text(text: str):
    """
    Teilt den Text in Chunks und erstellt einen FAISS-Vektorstore
    mit OpenAI-Embeddings. Gibt das VectorStore-Objekt zurück.
    """
    text_splitter = CharacterTextSplitter(separator="\n", chunk_size=1000, chunk_overlap=100)
    chunks = text_splitter.split_text(text)
    logging.info(f"Text in {len(chunks)} Chunks aufgeteilt.")

    embeddings = OpenAIEmbeddings()
    vectorstore = FAISS.from_texts(chunks, embedding=embeddings)
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
    st.title("📄 Paper-QA Chatbot mit OCR-Fallback (FAISS + EasyOCR)")

    # Falls du deinen OpenAI-Key nicht per st.secrets setzt, kannst du ihn hier aktivieren:
    # openai.api_key = st.secrets["OPENAI_API_KEY"]

    uploaded_files = st.file_uploader(
        "PDF-Dokument(e) hochladen (auch gescannte):",
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
                "- PDF ist rein gescannt und OCR (EasyOCR) liefert keine Ergebnisse.\n"
                "- PDF ist verschlüsselt oder geschützt.\n"
                "- Die Scanqualität ist sehr schlecht.\n\n"
                "Bitte überprüfen Sie die Dateien."
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
