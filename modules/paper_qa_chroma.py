import streamlit as st
import openai
import PyPDF2

from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma
from langchain.docstore.document import Document
from langchain.text_splitter import CharacterTextSplitter

openai.api_key = st.secrets["OPENAI_API_KEY"]

# Hilfsfunktion zum Laden eines Profils aus st.session_state
def load_profile(profile_name: str):
    if "profiles" in st.session_state:
        return st.session_state["profiles"].get(profile_name, None)
    return None

# Erzeugt eine Vektor-Datenbank aus einem langen Text (z. B. aus einem PDF)
def build_vectorstore_from_text(text: str):
    text_splitter = CharacterTextSplitter(
        separator="\n",
        chunk_size=1000,  # Länge in Zeichen
        chunk_overlap=100
    )
    chunks = text_splitter.split_text(text)
    docs = [Document(page_content=chunk) for chunk in chunks]
    embeddings = OpenAIEmbeddings(openai_api_key=openai.api_key)
    vectorstore = Chroma.from_documents(docs, embeddings)
    return vectorstore

# Erzeugt eine Vektor-Datenbank aus einer Liste von Paper-Dictionaries (z. B. aus dem Profil)
def build_vectorstore_from_papers(papers: list):
    docs = []
    for paper in papers:
        # Hier werden Titel und Abstract kombiniert – anpassbar nach Bedarf
        content = f"Title: {paper.get('Title', 'n/a')}\nAbstract: {paper.get('Abstract', 'n/a')}"
        docs.append(Document(page_content=content))
    embeddings = OpenAIEmbeddings(openai_api_key=openai.api_key)
    vectorstore = Chroma.from_documents(docs, embeddings)
    return vectorstore

# Extrahiert den Text aus einer hochgeladenen PDF-Datei
def extract_text_from_pdf(pdf_file) -> str:
    reader = PyPDF2.PdfReader(pdf_file)
    all_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            all_text.append(text)
    return "\n".join(all_text)

# Stellt eine Frage unter Einbeziehung eines gegebenen Kontextes an OpenAI
def ask_openai_context(question: str, context: str) -> str:
    system_prompt = (
        "Du bist ein hilfreicher KI-Assistent. "
        "Nutze den gegebenen Kontext, um die Frage bestmöglich zu beantworten. "
        "Wenn der Kontext unzureichend ist, sage 'Kann nicht sicher beantworten'."
    )
    user_prompt = f"KONTEXT:\n{context}\n\nFRAGE: {question}"
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=600,
        temperature=0.2,
    )
    return response.choices[0].message["content"].strip()

def main():
    st.title("Paper-QA mit Chroma (Vektor-Datenbank) + OpenAI")
    st.write("Untersuchen Sie Paper entweder per PDF-Upload oder anhand der im Profil gespeicherten Paper.")

    # Auswahl, ob man ein PDF hochladen oder die im Profil gespeicherten Paper nutzen möchte
    source_option = st.radio("Wählen Sie die Quelle der Paper:", ["PDF hochladen", "Profil gespeicherte Paper"])

    if source_option == "PDF hochladen":
        pdf_file = st.file_uploader("Bitte PDF hochladen", type=["pdf"])
        if pdf_file:
            pdf_text = extract_text_from_pdf(pdf_file)
            if pdf_text.strip():
                st.success("Text extrahiert! Erstelle Vektor-Datenbank ...")
                vectorstore = build_vectorstore_from_text(pdf_text)
                st.success("Vektor-Datenbank ist bereit! Stelle nun deine Frage.")
                question = st.text_input("Deine Frage:")
                if question and st.button("Antwort generieren"):
                    similar_docs = vectorstore.similarity_search(question, k=4)
                    with st.expander("Angefragte Chunks anzeigen"):
                        for i, d in enumerate(similar_docs, start=1):
                            st.markdown(f"**Chunk {i}**:\n{d.page_content}")
                    context_text = "\n\n".join([d.page_content for d in similar_docs])
                    answer = ask_openai_context(question, context_text)
                    st.write("### Antwort:")
                    st.write(answer)
            else:
                st.error("Konnte keinen Text aus der PDF extrahieren.")

    elif source_option == "Profil gespeicherte Paper":
        if "profiles" not in st.session_state or not st.session_state["profiles"]:
            st.error("Keine Profile vorhanden. Bitte erstellen Sie zuerst ein Profil mit gespeicherten Paper (z. B. via ChatGPT-Scoring).")
        else:
            profile_list = list(st.session_state["profiles"].keys())
            chosen_profile = st.selectbox("Profil wählen:", profile_list)
            profile_data = load_profile(chosen_profile)
            if not profile_data:
                st.error("Profil nicht gefunden oder leer.")
            else:
                if "selected_papers" in profile_data and profile_data["selected_papers"]:
                    papers = profile_data["selected_papers"]
                    st.write(f"Es wurden {len(papers)} Paper im Profil gefunden.")
                    vectorstore = build_vectorstore_from_papers(papers)
                    st.success("Vektor-Datenbank aus den Profil-Papern erstellt. Stellen Sie nun Ihre Frage.")
                    question = st.text_input("Deine Frage an die Profil-Paper:")
                    if question and st.button("Antwort generieren (Profil)"):
                        similar_docs = vectorstore.similarity_search(question, k=4)
                        with st.expander("Gefundene Dokumente anzeigen"):
                            for i, d in enumerate(similar_docs, start=1):
                                st.markdown(f"**Dokument {i}**:\n{d.page_content}")
                        context_text = "\n\n".join([d.page_content for d in similar_docs])
                        answer = ask_openai_context(question, context_text)
                        st.write("### Antwort:")
                        st.write(answer)
                else:
                    st.error("In diesem Profil sind keine gespeicherten Paper vorhanden. Bitte führen Sie zuerst das ChatGPT-Scoring aus, um Paper im Profil zu speichern.")

if __name__ == "__main__":
    main()
