import os
import PyPDF2
import openai
import streamlit as st
from dotenv import load_dotenv

# Nur einmal in diesem Skript aufrufen:
st.set_page_config(page_title="PaperAnalyzer", layout="wide")

# Umgebungsvariablen aus .env-Datei laden (optional, falls du deine Keys dort hinterlegst)
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
        Extrahiert Text aus einem PDF-Dokument (FileUploader-Objekt).
        
        :param pdf_file: PDF-Datei als FileUploader-Objekt
        :return: Extrahierter Text (string)
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
        Analysiert Text mit OpenAI API (oder einem entsprechenden Wrapper).
        
        :param text: Zu analysierender Text
        :param prompt_template: Prompt-Vorlage
        :param api_key: OpenAI API Key
        :return: Antwort von OpenAI
        """
        # Tokenlimit-Schutz
        if len(text) > 15000:
            text = text[:15000] + "..."
        
        prompt = prompt_template.format(text=text)
        
        # Falls du die offizielle openai-Bibliothek verwendest, 
        # müsstest du hier openai.api_key = api_key setzen und ChatCompletion.create(...) aufrufen
        client = openai.OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Du bist ein Experte für die Analyse wissenschaftlicher Paper, besonders im Bereich Side-Channel Analysis."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        
        return response.choices[0].message.content
    
    def summarize(self, text, api_key):
        """
        Erstellt eine Zusammenfassung des Papers.
        """
        prompt = (
            "Erstelle eine strukturierte Zusammenfassung des folgenden "
            "wissenschaftlichen Papers. Gliedere es in: Hintergrund, Methodik, "
            "Ergebnisse und Schlussfolgerungen. Verwende maximal 500 Wörter:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)
    
    def extract_key_findings(self, text, api_key):
        """
        Extrahiert die wichtigsten Erkenntnisse.
        """
        prompt = (
            "Extrahiere die 5 wichtigsten Erkenntnisse aus diesem wissenschaftlichen Paper "
            "im Bereich Side-Channel Analysis. Liste sie mit Bulletpoints auf:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)
    
    def identify_methods(self, text, api_key):
        """
        Identifiziert verwendete Methoden und Techniken zur Side-Channel-Analyse.
        """
        prompt = (
            "Identifiziere und beschreibe die im Paper verwendeten Methoden "
            "und Techniken zur Side-Channel-Analyse. Gib zu jeder Methode eine kurze Erklärung:\n\n{text}"
        )
        return self.analyze_with_openai(text, prompt, api_key)
    
    def evaluate_relevance(self, text, topic, api_key):
        """
        Bewertet die Relevanz des Papers für ein bestimmtes Thema.
        """
        prompt = (
            f"Bewerte die Relevanz dieses Papers für das Thema '{topic}' "
            f"auf einer Skala von 1-10. Begründe deine Bewertung:\n\n{{text}}"
        )
        return self.analyze_with_openai(text, prompt, api_key)

def main():
    st.title("📄 PaperAnalyzer - Analyse wissenschaftlicher Papers mit KI")
    
    # Einstellungen (Sidebar)
    st.sidebar.header("Einstellungen")
    
    # (1) OpenAI API Key
    api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=OPENAI_API_KEY or "")
    
    # (2) Modell auswählen
    model = st.sidebar.selectbox(
        "OpenAI-Modell",
        ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o"],
        index=0
    )
    
    # (3) Analyseart
    action = st.sidebar.radio(
        "Analyseart",
        ["Zusammenfassung", "Wichtigste Erkenntnisse", "Methoden & Techniken", "Relevanz-Bewertung"],
        index=0
    )
    
    # (4) Thema (nur für Relevanz-Bewertung)
    topic = ""
    if action == "Relevanz-Bewertung":
        topic = st.sidebar.text_input("Thema für Relevanz-Bewertung")
    
    # (5) PDF hochladen
    uploaded_file = st.file_uploader("PDF-Datei hochladen", type="pdf")
    
    # Analyzer
    analyzer = PaperAnalyzer(model=model)
    
    # Wenn sowohl PDF als auch API-Key vorliegen: zeige den "Analyse starten"-Button
    if uploaded_file and api_key:
        if st.button("Analyse starten"):
            # 1) PDF-Text extrahieren
            with st.spinner("Extrahiere Text aus PDF..."):
                text = analyzer.extract_text_from_pdf(uploaded_file)
                if not text.strip():
                    st.error("Es konnte kein Text aus der PDF extrahiert werden (evtl. nur eingescannt).")
                    st.stop()
                st.success("Text wurde erfolgreich extrahiert!")
            
            # 2) Analyse durchführen
            with st.spinner(f"Führe {action}-Analyse durch..."):
                if action == "Zusammenfassung":
                    result = analyzer.summarize(text, api_key)
                elif action == "Wichtigste Erkenntnisse":
                    result = analyzer.extract_key_findings(text, api_key)
                elif action == "Methoden & Techniken":
                    result = analyzer.identify_methods(text, api_key)
                elif action == "Relevanz-Bewertung":
                    if not topic:
                        st.error("Bitte Thema für Relevanz-Bewertung angeben!")
                        st.stop()
                    result = analyzer.evaluate_relevance(text, topic, api_key)
                
                # Ergebnis ausgeben
                st.subheader("Ergebnis der Analyse")
                st.markdown(result)
    else:
        # Falls kein Key da ist
        if not api_key:
            st.warning("Bitte einen OpenAI API-Key eingeben!")
        # Falls kein PDF
        elif not uploaded_file:
            st.info("Bitte eine PDF-Datei hochladen.")

if __name__ == "__main__":
    main()
