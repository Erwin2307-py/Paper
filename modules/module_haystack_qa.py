import streamlit as st
from haystack.document_stores import InMemoryDocumentStore
from haystack.nodes import BM25Retriever, FARMReader
from haystack.pipelines import ExtractiveQAPipeline
from haystack import Document

def module_haystack_qa():
    """
    Dieses Modul demonstriert eine einfache QA-Logik nur mit Haystack.
    - InMemoryDocumentStore + BM25Retriever
    - FARMReader (lokales Modell von Hugging Face)
    """

    st.title("Minimal Haystack QA (Nur Haystack)")

    # DocumentStore initialisieren (InMemory mit BM25-Index)
    if "doc_store" not in st.session_state:
        st.session_state.doc_store = InMemoryDocumentStore(use_bm25=True)

    # Retriever
    if "retriever" not in st.session_state:
        st.session_state.retriever = BM25Retriever(document_store=st.session_state.doc_store)

    # Reader
    if "reader" not in st.session_state:
        # Lokales Modell (du kannst auch ein anderes HF-Modell angeben)
        st.session_state.reader = FARMReader(
            model_name_or_path="deepset/roberta-base-squad2",
            use_gpu=False  # Auf Streamlit Cloud meist kein GPU-Support
        )

    # Pipeline aus Retriever + Reader
    pipeline = ExtractiveQAPipeline(reader=st.session_state.reader, retriever=st.session_state.retriever)

    st.markdown("### 1) Text eingeben und indexieren")
    text_input = st.text_area("Füge deinen Text hier ein:")
    if st.button("📥 Indexieren"):
        # Vorher alte Dokumente löschen
        st.session_state.doc_store.delete_documents()
        if text_input.strip():
            docs = [Document(content=text_input)]
            st.session_state.doc_store.write_documents(docs)
            st.success("Text wurde indexiert!")
        else:
            st.warning("Kein Text vorhanden.")

    st.markdown("### 2) Frage eingeben und Antwort erhalten")
    question = st.text_input("Tippe deine Frage ein:")
    if st.button("❓ Frage beantworten"):
        if not question.strip():
            st.warning("Bitte erst eine Frage eingeben.")
        else:
            # Pipeline ausführen
            result = pipeline.run(
                query=question,
                params={
                    "Retriever": {"top_k": 1},  # wie viele Passagen BM25 zurückgibt
                    "Reader": {"top_k": 1}      # wie viele mögliche Antworten der Reader ausgibt
                }
            )
            answers = result.get("answers", [])
            if answers:
                best_answer = answers[0].answer
                score = answers[0].score
                st.write(f"**Antwort**: {best_answer}")
                st.write(f"**Score**: {score:.4f}")
            else:
                st.info("Keine Antwort gefunden.")
