import os
import PyPDF2
import openai
import streamlit as st
from dotenv import load_dotenv

# Nur einmal aufrufen, wenn dieses Skript das "Hauptskript" ist.
# st.set_page_config(page_title="PaperAnalyzer", layout="wide")

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class PaperAnalyzer:
    def __init__(self, model="gpt-3.5-turbo"):
        """Initialisiert den Paper-Analyzer."""
        self.model = model

    def extract_text_from_pdf(self, pdf_file):
        """Extrahiert Text aus einem PDF-Dokument."""
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text

    def analyze_with_openai(self, text, prompt_template, api_key):
        """Analysiert den gegebenen Text via OpenAI (Wrapper oder offizielle Lib)."""
        # Tokenlimit-Schutz
        if len(text) > 15000:
            text = text[:15000] + "..."

        prompt = prompt_template.format(text=text)
        # Wenn du offiziell openai benutzt:
        # openai.api_key = api_key
        # response = openai.ChatCompletion.create(...)
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
        """Erstellt eine Zusammenfassung."""
        prompt = (
            "Erstelle eine strukturierte Zusammenfassung des folgenden "
            "wissenschaftlichen Papers. Gliedere es in: Hintergrund, Methodik, "
            "Ergebnisse und Schlussfolgerungen. Verwende maximal 500 Wörter:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def extract_key_findings(self, text, api_key):
        prompt = (
            "Extrahiere die 5 wichtigsten Erkenntnisse aus diesem "
            "wissenschaftlichen Paper im Bereich Side-Channel Analysis. "
            "Liste sie mit Bulletpoints auf:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def identify_methods(self, text, api_key):
        prompt = (
            "Identifiziere und beschreibe die im Paper verwendeten Methoden "
            "und Techniken zur Side-Channel-Analyse. Gib zu jeder Methode "
            "eine kurze Erklärung:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

    def evaluate_relevance(self, text, topic, api_key):
        prompt = (
            f"Bewerte die Relevanz dieses Papers für das Thema '{topic}' "
            f"auf einer Skala von 1-10. Begründe deine Bewertung:\n\n{{text}}"
        )
        return self.analyze_with_openai(text, prompt, api_key)


def main():
    st.title("📄 PaperAnalyzer - Immer mit Analyse-Button")

    # Seitenmenü
    st.sidebar.header("Einstellungen")
    api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=OPENAI_API_KEY or "")
    model = st.sidebar.selectbox(
        "OpenAI-Modell",
        ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o"],
        index=0
    )
    action = st.sidebar.radio(
        "Analyseart",
        ["Zusammenfassung", "Wichtigste Erkenntnisse", "Methoden & Techniken", "Relevanz-Bewertung"],
        index=0
    )
    topic = ""
    if action == "Relevanz-Bewertung":
        topic = st.sidebar.text_input("Thema für Relevanz-Bewertung")

    # PDF-Upload
    uploaded_file = st.file_uploader("PDF-Datei hochladen", type="pdf")

    # Analyzer
    analyzer = PaperAnalyzer(model=model)

    # Immer Button anzeigen
    st.write("Klicke auf den Button, um die Analyse zu starten (unabhängig vom Upload/API-Key).")

    if st.button("Analyse starten"):
        st.write("Analyse-Button geklickt!")
        
        # 1) Check: API Key
        if not api_key:
            st.error("Kein OpenAI API-Key eingetragen!")
            st.stop()

        # 2) Check: PDF
        if not uploaded_file:
            st.error("Keine PDF-Datei hochgeladen!")
            st.stop()

        # 3) Extrahiere Text
        with st.spinner("Extrahiere Text aus PDF..."):
            text = analyzer.extract_text_from_pdf(uploaded_file)
            if not text.strip():
                st.error("Keine oder nur leere Inhalte im PDF! Evtl. gescannt?")
                st.stop()
            st.success("Text wurde erfolgreich extrahiert!")

        # 4) Analyse ausführen
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
        st.info("Noch keine Analyse gestartet. Bitte Button klicken.")


if __name__ == "__main__":
    main()
