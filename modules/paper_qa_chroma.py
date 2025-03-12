import streamlit as st
import PyPDF2
import pdfplumber
import pytesseract
import openai
import logging

from PIL import Image
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings

# Hier der Community-Import
from langchain_community.vectorstores import Chroma

from streamlit_feedback import streamlit_feedback

logging.basicConfig(level=logging.INFO)

##############################################
# 1) PDF-Extraktion (PyPDF2 + OCR-Fallback)
##############################################

def extract_text_pypdf2(pdf_file) -> str:
    """
    Versucht, Text mit PyPDF2 auszulesen.
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

def extract_text_ocr(pdf_file) -> str:
    """
    Fallback-OCR mittels pdfplumber + pytesseract.
    Wandelt jede Seite in ein Bild um und wendet Tesseract an.
    ACHTUNG: Funktioniert nur, wenn Tesseract installiert ist.
    """
    ocr_text = ""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                # Seite als Bild rendern (resolution kann je nach Bedarf angepasst werden)
                pil_img = page.to_image(resolution=200).original
                # OCR mit pytesseract
                page_text = pytesseract.image_to_string(pil_img)
                if page_text.strip():
                    logging.debug(f"OCR auf Seite {page_index}: {len(page_text.strip())} Zeichen erkannt.")
                    ocr_text += page_text + "\n"
                else:
                    logging.debug(f"OCR auf Seite {page_index} lieferte keinen Text.")
    except Exception as e:
        logging.error(f"Fehler bei OCR via pdfplumber/pytesseract: {e}")
    return ocr_text.strip()

def extract_text_from_pdf(pdf_file) -> str:
    """
    Kombinierter Workflow:
      1) Versuch PyPDF2 (digitaler Text)
      2) Falls kein Text -> OCR-Fallback mit pdfplumber + pytesseract
    """
    text_pypdf = extract_text_pypdf2(pdf_file)
    if text_pypdf:
        logging.info("Erfolgreich Text mit PyPDF2 extrahiert.")
        return text_pypdf
    
    # PyPDF2 hat keinen oder nur leeren Text gefunden → OCR
    logging.info("Kein Text via PyPDF2 gefunden. Versuche OCR-Fallback ...")
    text_ocr = extract_text_ocr(pdf_file)
    if text_ocr:
        logging.info("OCR-Fallback war erfolgreich (pytesseract).")
        return text_ocr
    else:
        logging.warning("OCR-Fallback hat ebenfalls keinen Text gefunden.")
        return ""

##############################################
# 2) Chroma + OpenAI Q&A
##############################################

def create_vectorstore_from_text(text: str):
    """
    Teilt den Text in Chunks und erstellt eine Chroma-Datenbank
    (hier aus langchain_community.vectorstores) mit OpenAI-Embeddings.
    Gibt das VectorStore-Objekt zurück.
    """
    text_splitter = CharacterTextSplitter(separator="\n", chunk_size=1000, chunk_overlap=100)
    chunks = text_splitter.split_text(text)
    logging.info(f"Text in {len(chunks)} Chunks aufgeteilt.")

    embeddings = OpenAIEmbeddings()
    # Wichtig: Wir rufen das Chroma aus langchain_community auf
    vectorstore = Chroma.from_texts(chunks, embedding=embeddings)
    return vectorstore

def answer_question(query: str, vectorstore):
    """
    Sucht in der Vektordatenbank nach relevantem Kontext und erzeugt eine Antwort 
    auf die Nutzerfrage mit openai.ChatCompletion.
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
    Callback-Funktion für Feedback: Speichert die Benutzerbewertung (Daumen hoch/runter) im Chat-Verlauf.
    """
    feedback_value = st.session_state.get(f"feedback_{index}")
    st.session_state.history[index]["feedback"] = feedback_value
    logging.info(f"Feedback für Nachricht {index}: {feedback_value}")

##############################################
# 4) Haupt-App
##############################################

def main():
    st.title("📄 Paper-QA Chatbot mit OCR-Fallback (Community-Chroma)")

    # Optional: OpenAI-API-Key
    # openai.api_key = st.secrets["OPENAI_API_KEY"]

    # PDF Upload
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
                "- PDF ist rein gescannt und Tesseract ist nicht oder falsch installiert.\n"
                "- PDF ist verschlüsselt oder geschützt.\n"
                "- OCR erkennt nur leere Ergebnisse (z. B. sehr schlechte Scanqualität).\n\n"
                "Bitte überprüfen Sie die Dateien oder konfigurieren Sie Tesseract."
            )

    # Chatverlauf initialisieren
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
