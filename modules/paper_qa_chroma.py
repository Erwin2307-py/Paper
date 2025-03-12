import streamlit as st
import PyPDF2
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma
import openai
import logging

# Anforderungen umgesetzt:
# 1. LLM-Integration (OpenAI ChatCompletion mit gpt-3.5-turbo)
# 2. UI-Funktionen: st.file_uploader, st.chat_input, st.feedback
# 3. Datenverarbeitung: PyPDF2 (PDF-Text), CharacterTextSplitter, Chroma, OpenAIEmbeddings
# 4. Chat-Flow: st.session_state (Verlauf), similarity_search(k=4), kontextbasierte Antwort via ChatCompletion
# 5. Optimierungen: modulare Funktionen, Statusmeldungen (st.success, st.error), Logging für Debugging

# Hinweis: Erfordert Streamlit >= 1.42.0 (für st.chat_input und st.feedback) 
# sowie installierte Pakete: PyPDF2, langchain, chromadb, openai

logging.basicConfig(level=logging.INFO)

# Optional: OpenAI API-Key setzen, falls nicht über Umgebungsvariable/Secrets konfiguriert
# openai.api_key = st.secrets["OPENAI_API_KEY"]

def extract_text_from_pdf(file) -> str:
    """
    Extrahiert den gesamten Text einer PDF-Datei mittels PyPDF2.
    """
    try:
        reader = PyPDF2.PdfReader(file)
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
    # Text in überlappende Abschnitte aufteilen (Chunking)
    text_splitter = CharacterTextSplitter(separator="\n", chunk_size=1000, chunk_overlap=100)
    chunks = text_splitter.split_text(text)
    logging.info(f"Text in {len(chunks)} Chunks aufgeteilt.")
    # Vektorstore mit Chroma und OpenAI Embeddings erstellen
    embeddings = OpenAIEmbeddings()  # nutzt standardmäßig das OpenAI Embedding-Modell
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
    # Kontext aus den gefundenen Passagen zusammenstellen
    context = "\n".join([d.page_content for d in docs])
    # Nachrichten für das Chat-Modell vorbereiten
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

# Streamlit App UI
st.title("📄 Paper-QA Chatbot")

# PDF Upload
uploaded_files = st.file_uploader("PDF-Dokumente hochladen", type=["pdf"], accept_multiple_files=True)
if uploaded_files:
    # Gesamten Text aus allen hochgeladenen PDFs extrahieren
    all_text = ""
    for file in uploaded_files:
        file_text = extract_text_from_pdf(file)
        if file_text:
            all_text += file_text + "\n"
    if all_text:
        # Vektor-Datenbank einmalig erstellen und im Session State speichern
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
            # Feedback-Widget für KI-Antwort anzeigen (Daumen hoch/runter)
            feedback = msg.get("feedback")
            st.session_state[f"feedback_{i}"] = feedback  # aktuellen Feedback-Wert setzen
            st.feedback(
                "thumbs",
                key=f"feedback_{i}",
                disabled=feedback is not None,
                on_change=save_feedback,
                args=(i,)
            )

# Neue Frage-Eingabe (Chat-Eingabefeld)
if prompt := st.chat_input("Frage zu den hochgeladenen Papers stellen..."):
    # Nutzerfrage anzeigen und zum Verlauf hinzufügen
    with st.chat_message("user"):
        st.write(prompt)
    st.session_state.history.append({"role": "user", "content": prompt})
    # Prüfen, ob bereits eine Vektor-Datenbank erstellt wurde
    if "vectorstore" not in st.session_state:
        st.error("Bitte laden Sie zuerst ein PDF hoch, bevor Sie Fragen stellen.")
    else:
        # KI-Antwort unter Verwendung des Paper-Kontextes generieren
        answer = answer_question(prompt, st.session_state.vectorstore)
        # KI-Antwort im Chat anzeigen
        with st.chat_message("assistant"):
            st.write(answer)
            st.feedback(
                "thumbs", 
                key=f"feedback_{len(st.session_state.history)}", 
                on_change=save_feedback, 
                args=(len(st.session_state.history),)
            )
        # Antwort im Verlauf speichern
        st.session_state.history.append({"role": "assistant", "content": answer})
