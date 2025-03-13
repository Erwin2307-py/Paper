import os
import PyPDF2
import openai
import streamlit as st
from dotenv import load_dotenv

# Entferne oder kommentiere aus, wenn du das Skript
# als Untermodul in einer größeren App verwendest:
# st.set_page_config(page_title="PaperAnalyzer", layout="wide")

# Umgebungsvariablen aus .env-Datei laden
load_dotenv()

# OpenAI API-Key aus .env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class PaperAnalyzer:
    def __init__(self, model="gpt-3.5-turbo"):
        """
        Initialisiert den Paper-Analyzer
        
        :param model: OpenAI-Modell für die Analyse
        """
        self.model = model

    def extract_text_from_pdf(self, pdf_file):
        """
        Extrahiert Text aus einem PDF-Dokument (FileUploader-Objekt)
        und gibt den gesamten Text als String zurück.
        """
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text

    def analyze_with_openai(self, text, prompt_template, api_key):
        """
        Analysiert den gegebenen Text mit OpenAI über dein
        (vermutlich) eigenes Wrapper-Objekt openai.OpenAI(api_key=...).

        Wenn du die offizielle 'openai'-Bibliothek von PyPI nutzt,
        ersetze das hier durch:
        
            openai.api_key = api_key
            response = openai.ChatCompletion.create(...)
        
        statt openai.OpenAI(api_key=...).
        """
        # Tokenlimit-Schutz
        if len(text) > 15000:
            text = text[:15000] + "..."

        prompt = prompt_template.format(text=text)

        # Beispiel: Wrapper-Client, NICHT offizielle openai-Bibliothek
        client = openai.OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Du bist ein Experte für die Analyse wissenschaftlicher Paper, "
                        "besonders im Bereich Side-Channel Analysis."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        return response.choices[0].message.content

    def summarize(self, text, api_key):
        """Erstellt eine Zusammenfassung des Papers"""
        prompt = (
            "Erstelle eine strukturierte Zusammenfassung des folgenden "
            "wissenschaftlichen Papers. Gliedere es in: Hintergrund, Methodik, "
            "Ergebnisse und Schlussfolgerungen. Verwende maximal 500 Wörter:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)
    
    def extract_key_findings(self, text, api_key):
        """Extrahiert die wichtigsten Erkenntnisse"""
        prompt = (
            "Extrahiere die 5 wichtigsten Erkenntnisse aus diesem "
            "wissenschaftlichen Paper im Bereich Side-Channel Analysis. "
            "Liste sie mit Bulletpoints auf:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)
    
    def identify_methods(self, text, api_key):
        """Identifiziert verwendete Methoden und Techniken"""
        prompt = (
            "Identifiziere und beschreibe die im Paper verwendeten Methoden "
            "und Techniken zur Side-Channel-Analyse. Gib zu jeder Methode "
            "eine kurze Erklärung:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)
    
    def evaluate_relevance(self, text, topic, api_key):
        """Bewertet die Relevanz des Papers für ein bestimmtes Thema"""
        prompt = (
            f"Bewerte die Relevanz dieses Papers für das Thema '{topic}' "
            f"auf einer Skala von 1-10. Begründe deine Bewertung:\n\n{{text}}"
        )
        return self.analyze_with_openai(text, prompt, api_key)


def main():
    st.title("📄 PaperAnalyzer - Analyse wissenschaftlicher Papers mit KI")

    # Seitenmenü
    st.sidebar.header("Einstellungen")
    
    # 1) API-Key erfassen
    api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=OPENAI_API_KEY or "")
    
    # 2) Modell-Auswahl
    model = st.sidebar.selectbox(
        "OpenAI-Modell",
        options=["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o"],
        index=0
    )
    
    # 3) Analyseart
    action = st.sidebar.radio(
        "Analyseart",
        ["Zusammenfassung", "Wichtigste Erkenntnisse", "Methoden & Techniken", "Relevanz-Bewertung"],
        index=0
    )
    
    # 4) Thema bei Relevanz-Bewertung
    topic = ""
    if action == "Relevanz-Bewertung":
        topic = st.sidebar.text_input("Thema für Relevanz-Bewertung")
    
    # 5) PDF-Upload
    uploaded_file = st.file_uploader("PDF-Datei hochladen", type="pdf")
    
    # Analyzer-Objekt erstellen
    analyzer = PaperAnalyzer(model=model)
    
    # 6) Wenn Datei hochgeladen und API-KEY vorhanden => Analyse
    if uploaded_file and api_key:
        if st.button("Analyse starten"):
            with st.spinner("Extrahiere Text aus PDF..."):
                text = analyzer.extract_text_from_pdf(uploaded_file)
                if not text.strip():
                    st.error("Keine oder nur leere Inhalte im PDF! Evtl. gescannt?")
                    return
                st.success("Text wurde erfolgreich extrahiert!")
            
            with st.spinner(f"Führe {action}-Analyse durch..."):
                if action == "Zusammenfassung":
                    result = analyzer.summarize(text, api_key)
                elif action == "Wichtigste Erkenntnisse":
                    result = analyzer.extract_key_findings(text, api_key)
                elif action == "Methoden & Techniken":
                    result = analyzer.identify_methods(text, api_key)
                elif action == "Relevanz-Bewertung":
                    if not topic:
                        st.error("Bitte ein Thema für die Relevanz-Bewertung angeben!")
                        st.stop()
                    result = analyzer.evaluate_relevance(text, topic, api_key)
                
                st.subheader("Ergebnis der Analyse")
                st.markdown(result)
    else:
        if not api_key:
            st.warning("Bitte OpenAI API-Key eingeben!")
        elif not uploaded_file:
            st.info("Bitte lade eine PDF-Datei hoch!")


if __name__ == "__main__":
    main()
