import streamlit as st
import PyPDF2
import logging
from io import BytesIO

from haystack.document_stores import FAISSDocumentStore
from haystack.nodes import DensePassageRetriever, FARMReader
from haystack.pipelines import ExtractiveQAPipeline
from haystack.schema import Document

logging.basicConfig(level=logging.INFO)

# Funktion zur PDF-Extraktion (nur digitale PDFs)
def extract_text_from_pdf(pdf_file) -> str:
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

st.title("Medizinische Paper QA mit Haystack")

uploaded_files = st.file_uploader("Lade digitale PDF-Dateien hoch:", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    # Erstelle Haystack-Dokumente aus den hochgeladenen PDFs
    docs = []
    for file in uploaded_files:
        text = extract_text_from_pdf(file)
        if text:
            docs.append(Document(content=text, meta={"name": file.name}))
    if not docs:
        st.error("Aus den hochgeladenen PDFs konnte kein Text extrahiert werden. Bitte lade maschinenlesbare PDFs hoch.")
    else:
        st.success(f"Text aus {len(docs)} PDFs extrahiert.")

        # Erstelle einen FAISS-Dokumentenspeicher (in-memory)
        document_store = FAISSDocumentStore(embedding_dim=768, faiss_index_factory_str="Flat")
        document_store.write_documents([doc.to_dict() for doc in docs])
        
        # Initialisiere Dense Passage Retriever
        retriever = DensePassageRetriever(
            document_store=document_store,
            query_embedding_model="facebook/dpr-question_encoder-single-nq-base",
            passage_embedding_model="facebook/dpr-ctx_encoder-single-nq-base",
            use_gpu=False,
            embed_title=True,
        )
        # Aktualisiere die Embeddings im DocumentStore
        document_store.update_embeddings(retriever)
        
        # Initialisiere einen Reader (z. B. FARMReader)
        reader = FARMReader(model_name_or_path="deepset/roberta-base-squad2", use_gpu=False)
        
        # Erstelle die QA-Pipeline
        qa_pipeline = ExtractiveQAPipeline(reader, retriever)
        
        query = st.text_input("Stelle eine Frage zu den hochgeladenen Papers:")
        if query:
            result = qa_pipeline.run(query=query, params={"Retriever": {"top_k": 10}, "Reader": {"top_k": 5}})
            if result["answers"]:
                st.markdown("### Antwort:")
                st.write(result["answers"][0].answer)
                st.markdown("### Kontext:")
                for ans in result["answers"]:
                    st.write(ans.context)
            else:
                st.error("Keine Antwort gefunden.")
