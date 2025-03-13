import os
import PyPDF2
import openai
import streamlit as st
from dotenv import load_dotenv

# --------------------------------------------
# KEIN st.set_page_config(...) hier,
# das passiert im Hauptskript.
# --------------------------------------------

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ------------------------------
# Session State-Keys definieren
# ------------------------------
if "pdf_text" not in st.session_state:
    st.session_state["pdf_text"] = None

if "last_uploaded_filename" not in st.session_state:
    st.session_state["last_uploaded_filename"] = None


class PaperAnalyzer:
    def __init__(self, model="gpt-3.5-turbo"):
        """
        Initialisiert den Paper-Analyzer
        """
        self.model = model
    
    def extract_text_from_pdf(self, pdf_file):
        """
        Extrahiert Text aus einem PDF-Dokument (FileUploader-Objekt) 
        und gibt den gesamten Text zurück.
        """
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    
    def analyze_with_openai(self, text, prompt_template, api_key):
        """
        Analysiert Text mit OpenAI API
        """
        if len(text) > 15000:
            text = text[:15000] + "..."
        
        prompt = prompt_template.format(text=text)
        
        # ACHTUNG: Du verwendest client = openai.OpenAI(api_key=...)
        # Das ist NICHT Teil der offiziellen openai-Bibliothek.
        # Möglicherweise ein Wrapper. 
        # Mit der "normalen" Bibliothek wäre: openai.api_key = api_key; ...
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
    
    st.sidebar.header("Einstellungen")
    
    # 1) OpenAI API Key
    api_key = st.sidebar.text_input("OpenAI API Key", type="password", value=OPENAI_API_KEY or "")
    
    # 2) Modell-Auswahl
    model = st.sidebar.selectbox(
        "OpenAI-Modell",
        options=["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o"],
        index=0
    )
    
    # 3) Analyseart (Radio-Buttons)
    action = st.sidebar.radio(
        "Analyseart",
        options=["Zusammenfassung", "Wichtigste Erkenntnisse", "Methoden & Techniken", "Relevanz-Bewertung"],
        index=0
    )
    
    # 4) Optionales Thema
    topic = ""
    if action == "Relevanz-Bewertung":
        topic = st.sidebar.text_input("Thema für Relevanz-Bewertung")
    
    # 5) PDF hochladen
    uploaded_file = st.file_uploader("PDF-Datei hochladen", type="pdf")
    
    analyzer = PaperAnalyzer(model=model)

    # ---------------------------------------------
    # Falls neue Datei hochgeladen wird => Text extrahieren + in Session State
    # ---------------------------------------------
    if uploaded_file is not None:
        # Nur wenn sich der Dateiname ändert oder Session State noch nichts gespeichert hat
        if (
            uploaded_file.name != st.session_state["last_uploaded_filename"] 
            or st.session_state["pdf_text"] is None
        ):
            with st.spinner("Extrahiere Text aus PDF..."):
                st.session_state["pdf_text"] = analyzer.extract_text_from_pdf(uploaded_file)
                st.session_state["last_uploaded_filename"] = uploaded_file.name
            st.success(f"Text aus {uploaded_file.name} wurde extrahiert.")

    # ---------------------------------------------
    # Jetzt prüfen, ob wir Text + API Key haben => Button für Analyse anzeigen
    # ---------------------------------------------
    if st.session_state["pdf_text"] and api_key:
        # Button: Analyse starten
        if st.button("Analyse starten"):
            with st.spinner(f"Führe {action}-Analyse durch..."):
                text = st.session_state["pdf_text"]  # PDF-Inhalt aus Session State
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
                
                st.subheader("Ergebnis der Analyse")
                st.markdown(result)
    else:
        # Falls kein API-Key: Hinweis anzeigen
        if not api_key:
            st.warning("Bitte geben Sie Ihren OpenAI API-Key ein!")
        # Falls keine PDF hochgeladen: Info anzeigen
        elif not uploaded_file:
            st.info("Bitte laden Sie eine PDF-Datei hoch! (Keine gefunden)")
        # Falls hochgeladen_file da, aber doch kein Text: Debug-Hinweis
        else:
            st.info("PDF-Datei hochgeladen, aber kein Text extrahiert.")


if __name__ == "__main__":
    main()
