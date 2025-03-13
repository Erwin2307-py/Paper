import os
import PyPDF2
import openai
import streamlit as st
from dotenv import load_dotenv

# Seitentitel und Layout
st.set_page_config(page_title="PaperAnalyzer", layout="wide")

# Umgebungsvariablen aus .env-Datei laden
load_dotenv()

# OpenAI API-Key aus Umgebungsvariablen
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
        Extrahiert Text aus einem PDF-Dokument
        
        :param pdf_file: PDF-Datei als FileUploader-Objekt
        :return: Extrahierter Text
        """
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text

    def analyze_with_dummy_logic(self, text, task_info):
        """
        Dummy-Analyse, falls kein gültiger OpenAI-API-Key vorliegt.
        
        :param text: Extrahierter Volltext aus dem PDF
        :param task_info: Kurze Beschreibung der Aufgabe (z.B. "Zusammenfassung" usw.)
        :return: Simulierter Ergebnis-String
        """
        # Beispielhafter "Dummy"-Ansatz: Zeichen- und Wortanzahl ermitteln
        num_chars = len(text)
        num_words = len(text.split())
        dummy_response = (
            f"**DUMMY-Analyse für: {task_info}**\n\n"
            f"Anzahl Zeichen im Text: {num_chars}\n"
            f"Anzahl Wörter im Text: {num_words}\n\n"
            f"Dies ist eine simulierte Ausgabe, da kein OpenAI API-Key vorhanden ist "
            f"oder die KI-Analyse nicht aufgerufen wurde."
        )
        return dummy_response

    def analyze_with_openai(self, text, prompt_template, api_key):
        """
        Analysiert Text mit OpenAI API
        
        :param text: Zu analysierender Text
        :param prompt_template: Vorlage für den Prompt
        :param api_key: OpenAI API Key
        :return: Antwort von OpenAI
        """
        # Text kürzen, falls er zu lang ist (Token-Limit beachten)
        if len(text) > 15000:
            text = text[:15000] + "..."
        
        prompt = prompt_template.format(text=text)

        # Wichtig: openai muss mit openai.api_key=... genutzt werden
        openai.api_key = api_key
        
        response = openai.ChatCompletion.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Du bist ein Experte für die Analyse wissenschaftlicher Paper, besonders im Bereich Side-Channel Analysis."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        
        return response.choices[0].message.content
    
    def summarize(self, text, api_key):
        """Erstellt eine Zusammenfassung des Papers"""
        prompt = (
            "Erstelle eine strukturierte Zusammenfassung des folgenden wissenschaftlichen Papers. "
            "Gliedere es in: Hintergrund, Methodik, Ergebnisse und Schlussfolgerungen. "
            "Verwende maximal 500 Wörter:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)
    
    def extract_key_findings(self, text, api_key):
        """Extrahiert die wichtigsten Erkenntnisse"""
        prompt = (
            "Extrahiere die 5 wichtigsten Erkenntnisse aus diesem wissenschaftlichen Paper "
            "im Bereich Side-Channel Analysis. Liste sie mit Bulletpoints auf:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)
    
    def identify_methods(self, text, api_key):
        """Identifiziert verwendete Methoden und Techniken"""
        prompt = (
            "Identifiziere und beschreibe die im Paper verwendeten Methoden und Techniken zur Side-Channel-Analyse. "
            "Gib zu jeder Methode eine kurze Erklärung:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)
    
    def evaluate_relevance(self, text, topic, api_key):
        """Bewertet die Relevanz des Papers für ein bestimmtes Thema"""
        prompt = (
            f"Bewerte die Relevanz dieses Papers für das Thema '{topic}' auf einer Skala von 1-10. "
            "Begründe deine Bewertung:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

def main():
    st.title("📄 PaperAnalyzer - Analyse wissenschaftlicher Papers mit KI")
    
    # Seitenmenü
    st.sidebar.header("Einstellungen")
    
    # OpenAI API Key
    api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=OPENAI_API_KEY or "")
    
    # Modellauswahl
    model = st.sidebar.selectbox(
        "OpenAI-Modell",
        options=["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o"],
        index=0
    )
    
    # Analyseart
    action = st.sidebar.radio(
        "Analyseart",
        options=["Zusammenfassung", "Wichtigste Erkenntnisse", "Methoden & Techniken", "Relevanz-Bewertung"],
        index=0
    )
    
    # Thema für Relevanz-Bewertung
    topic = ""
    if action == "Relevanz-Bewertung":
        topic = st.sidebar.text_input("Thema für Relevanz-Bewertung")
    
    # PDF-Upload
    uploaded_file = st.file_uploader("PDF-Datei hochladen", type="pdf")
    
    # Initialize analyzer
    analyzer = PaperAnalyzer(model=model)
    
    if uploaded_file:
        # Button zum Starten der Analyse
        if st.button("Analyse starten"):
            # Schritt 1: PDF-Text extrahieren
            with st.spinner("Extrahiere Text aus PDF..."):
                text = analyzer.extract_text_from_pdf(uploaded_file)
                st.success("Text wurde erfolgreich extrahiert!")
            
            # Schritt 2: Prüfen, ob API-Key vorhanden -> AI oder Dummy
            if not api_key:
                st.warning("Kein gültiger OpenAI API-Key eingegeben. Es wird eine Dummy-Analyse durchgeführt.")
                # Dummy-Analyse durchführen
                task_info = action if action != "Relevanz-Bewertung" else f"{action} (Topic: {topic})"
                result = analyzer.analyze_with_dummy_logic(text, task_info)
            else:
                # OpenAI-Analyse
                with st.spinner(f"Führe {action}-Analyse durch..."):
                    if action == "Zusammenfassung":
                        result = analyzer.summarize(text, api_key)
                    elif action == "Wichtigste Erkenntnisse":
                        result = analyzer.extract_key_findings(text, api_key)
                    elif action == "Methoden & Techniken":
                        result = analyzer.identify_methods(text, api_key)
                    elif action == "Relevanz-Bewertung":
                        if not topic:
                            st.error("Bitte geben Sie ein Thema für die Relevanz-Bewertung an!")
                            st.stop()
                        result = analyzer.evaluate_relevance(text, topic, api_key)

            # Schritt 3: Ergebnis anzeigen
            st.subheader("Ergebnis der Analyse")
            st.markdown(result)
    else:
        st.info("Bitte laden Sie eine PDF-Datei hoch, um zu starten.")

if __name__ == "__main__":
    main()
