import os
import PyPDF2
import openai
import streamlit as st
from dotenv import load_dotenv

# Nur verwenden, wenn es ein eigenständiges Skript ist.
# Falls es in eine andere App importiert wird, bitte auskommentieren!
st.set_page_config(page_title="PaperAnalyzer", layout="wide")

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ------------------------------------------------------
# Session State: Wir halten hier den extrahierten PDF-Text
# und das letzte geladene Dateiname fest
# ------------------------------------------------------
if "pdf_text" not in st.session_state:
    st.session_state["pdf_text"] = None

if "last_uploaded_filename" not in st.session_state:
    st.session_state["last_uploaded_filename"] = None

if "analysis_result" not in st.session_state:
    st.session_state["analysis_result"] = None


class PaperAnalyzer:
    def __init__(self, model="gpt-3.5-turbo"):
        """Initialisiert den PaperAnalyzer."""
        self.model = model

    def extract_text_from_pdf(self, pdf_file):
        """Extrahiert Text aus einem PDF-Dokument und gibt ihn zurück."""
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text

    def analyze_with_openai(self, text, prompt_template, api_key):
        """
        Analysiert den gegebenen Text via (vermutlich) openai.OpenAI(api_key=...).
        Falls du die offizielle openai-Bibliothek verwendest, musst du 
        openai.api_key = api_key setzen und ChatCompletion.create(...) aufrufen.
        """
        if len(text) > 15000:
            text = text[:15000] + "..."

        prompt = prompt_template.format(text=text)

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
    st.title("PaperAnalyzer – PDF hochladen & Analyse starten")

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

    uploaded_file = st.file_uploader("PDF-Datei hochladen", type="pdf")

    analyzer = PaperAnalyzer(model=model)

    # Wenn eine neue Datei hochgeladen wurde (oder gar keine in session_state war),
    # dann extrahiere sofort den Text und speichere ihn in session_state["pdf_text"].
    if uploaded_file is not None:
        # Prüfe, ob es eine andere Datei als die zuletzt geladene ist
        if (
            uploaded_file.name != st.session_state["last_uploaded_filename"]
            or st.session_state["pdf_text"] is None
        ):
            with st.spinner(f"PDF '{uploaded_file.name}' wird gelesen..."):
                text = analyzer.extract_text_from_pdf(uploaded_file)
                st.session_state["pdf_text"] = text
                st.session_state["last_uploaded_filename"] = uploaded_file.name
                st.session_state["analysis_result"] = None  # ggf. altes Ergebnis löschen
            if text.strip():
                st.success("PDF-Text erfolgreich extrahiert.")
            else:
                st.warning("Die PDF scheint keinen auslesbaren Text zu enthalten.")
    
    # Button zum Starten der Analyse
    if st.button("Analyse starten"):
        # Falls kein Key eingegeben
        if not api_key:
            st.error("Kein OpenAI API-Key vorhanden!")
            st.stop()

        # Falls keine PDF (bzw. kein Text) vorhanden
        if not st.session_state["pdf_text"] or not st.session_state["pdf_text"].strip():
            st.error("Kein Text vorhanden – bitte eine valide PDF hochladen!")
            st.stop()

        # Analyse durchführen
        with st.spinner(f"Führe {action}-Analyse durch..."):
            if action == "Zusammenfassung":
                result = analyzer.summarize(st.session_state["pdf_text"], api_key)
            elif action == "Wichtigste Erkenntnisse":
                result = analyzer.extract_key_findings(st.session_state["pdf_text"], api_key)
            elif action == "Methoden & Techniken":
                result = analyzer.identify_methods(st.session_state["pdf_text"], api_key)
            elif action == "Relevanz-Bewertung":
                if not topic:
                    st.error("Bitte ein Thema für die Relevanz-Bewertung angeben!")
                    st.stop()
                result = analyzer.evaluate_relevance(st.session_state["pdf_text"], topic, api_key)

        # Ergebnis in Session-State merken, um es auch nach Rerun noch zu haben
        st.session_state["analysis_result"] = result

    # Falls bereits ein Analyseergebnis vorliegt, anzeigen
    if st.session_state["analysis_result"]:
        st.subheader("Ergebnis der Analyse")
        st.markdown(st.session_state["analysis_result"])


if __name__ == "__main__":
    main()
