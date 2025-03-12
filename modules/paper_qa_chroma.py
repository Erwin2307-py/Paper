import streamlit as st
import PyPDF2
import openai
import logging

from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma

# Wichtig: Korrekt streamlit_feedback importieren
from streamlit_feedback import streamlit_feedback

logging.basicConfig(level=logging.INFO)

# Optional: Falls du den OpenAI-API-Key aus secrets beziehen möchtest:
# openai.api_key = st.secrets["OPENAI_API_KEY"]


def extract_text_from_pdf(pdf_file) -> str:
    """
    Extrahiert den gesamten Text einer PDF-Datei mittels PyPDF2.
    """
    try:
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        logging.error(f"Fehler beim Lesen der PDF: {e}")
        return ""


def create_vectorstore_from_text(text: str):
    """
    Zerteilt den Text in Chunks und erstellt eine Chroma Vektor-Datenbank mit OpenAI-Embeddings.
    Gibt das erstellte Vektorstore-Objekt zurück.
    """
    text_splitter = CharacterTextSplitter(separator="\n", chunk_size=1000, chunk_overlap=100)
    chunks = text_splitter.split_text(text)
    logging.info(f"Text in {len(chunks)} Chunks aufgeteilt.")

    embeddings = OpenAIEmbeddings()  # nutzt standardmäßig OpenAI-Embeddings
    vectorstore = Chroma.from_texts(chunks, embedding=embeddings, persist_directory=None)
    return vectorstore


def answer_question(query: str, vectorstore):
    """
    Sucht in der Vektordatenbank nach relevantem Kontext und erzeugt eine Antwort 
    auf die Nutzerfrage mittels OpenAI ChatCompletion.
    Gibt die erzeugte Antwort als String zurück.
    """
    # Relevante Dokument-Passagen per Semantik-Suche abrufen
    docs = vectorstore.similarity_search(query, k=4)
    logging.info(f"{len(docs)} relevante Textstellen für die Anfrage gefunden.")

    # Kontext zusammenstellen
    context = "\n".join([d.page_content for d in docs])

    # System- und User-Prompts
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


def save_feedback(index):
    """
    Callback-Funktion für Feedback: Speichert die Benutzerbewertung (Daumen hoch/runter) im Chat-Verlauf.
    """
    feedback_value = st.session_state.get(f"feedback_{index}")
    st.session_state.history[index]["feedback"] = feedback_value
    logging.info(f"Feedback für Nachricht {index}: {feedback_value}")


def main():
    st.title("📄 Paper-QA Chatbot")

    # PDF-Upload
    uploaded_files = st.file_uploader(
        "PDF-Dokumente hochladen", 
        type=["pdf"], 
        accept_multiple_files=True
    )

    if uploaded_files:
        all_text = ""
        for file in uploaded_files:
            file_text = extract_text_from_pdf(file)
            if file_text:
                all_text += file_text + "\n"

        if all_text.strip():
            # Einmalig Vektor-Datenbank im Session State speichern
            vectorstore = create_vectorstore_from_text(all_text)
            st.session_state.vectorstore = vectorstore
            st.success("Wissensdatenbank aus den hochgeladenen Papers wurde erfolgreich erstellt.")
            logging.info("Vektorstore erstellt und im Session-State gespeichert.")
        else:
            st.error("Es konnte kein Text aus den PDFs extrahiert werden. Bitte überprüfen Sie die Dateien.")

    # Chat-Verlauf initialisieren
    if "history" not in st.session_state:
        st.session_state.history = []

    # Bisherigen Chat-Verlauf anzeigen
    for i, msg in enumerate(st.session_state.history):
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant":
                # Feedback-Widget für KI-Antwort
                feedback = msg.get("feedback")
                st.session_state[f"feedback_{i}"] = feedback  # vorhandenen Wert einstellen
                streamlit_feedback(
                    feedback_type="thumbs",
                    key=f"feedback_{i}",
                    disabled=feedback is not None,
                    on_change=save_feedback,
                    args=(i,),
                )

    # Neue Frage per Chat-Eingabe
    if prompt := st.chat_input("Frage zu den hochgeladenen Papers stellen..."):
        # Nutzerfrage anzeigen und speichern
        with st.chat_message("user"):
            st.write(prompt)
        st.session_state.history.append({"role": "user", "content": prompt})

        # Prüfen, ob Vektor-Datenbank vorhanden
        if "vectorstore" not in st.session_state:
            st.error("Bitte lade mindestens ein PDF hoch, bevor du Fragen stellst.")
        else:
            # KI-Antwort erzeugen
            answer = answer_question(prompt, st.session_state.vectorstore)
            with st.chat_message("assistant"):
                st.write(answer)
                # Feedback-Widget für diese neue Antwort
                streamlit_feedback(
                    feedback_type="thumbs",
                    key=f"feedback_{len(st.session_state.history)}",
                    on_change=save_feedback,
                    args=(len(st.session_state.history),),
                )
            # Antwort im Verlauf speichern
            st.session_state.history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
