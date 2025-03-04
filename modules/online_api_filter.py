import streamlit as st
import requests
import openai
import pandas as pd
import os

##############################################################################
# 1) ChatGPT-Verbindungscheck (optional)
##############################################################################

def check_chatgpt_connection():
    """
    Prüft, ob die OpenAI-API (ChatGPT) erreichbar ist, indem ein kurzer Prompt
    an das Modell gpt-3.5-turbo geschickt wird.
    Erfordert, dass ein OPENAI_API_KEY in st.secrets['OPENAI_API_KEY'] hinterlegt ist.
    """
    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        return False
    try:
        openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "user",
                    "content": "Short connectivity test. Reply with any short message."
                }
            ],
            max_tokens=10,
            temperature=0
        )
        return True
    except Exception:
        return False

##############################################################################
# 2) Gene-Loader: Liest ab C3 (Spalte C, Zeile 3) im gewählten Sheet
##############################################################################

def load_genes_from_excel(sheet_name: str) -> list:
    """
    Lädt die Gene ab Zelle C3 (Spalte C, Zeile 3) aus dem gewählten Sheet in `modules/genes.xlsx`.
    
    Annahmen:
      - 'genes.xlsx' liegt direkt im Ordner 'modules'.
      - Ab Zeile 3 (Index=2) und in Spalte C (Index=2) stehen die Gen-Namen.
    """
    excel_path = os.path.join("modules", "genes.xlsx")
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        # df.iloc[2:, 2] bedeutet: Ab Zeile 3, Spalte C
        gene_series = df.iloc[2:, 2]

        # NaN-Werte entfernen und in String umwandeln
        gene_list = gene_series.dropna().astype(str).tolist()
        return gene_list
    except Exception as e:
        st.error(f"Fehler beim Laden der Excel-Datei: {e}")
        return []

##############################################################################
# 3) ChatGPT-Funktion zum Filtern
##############################################################################

def check_genes_in_text_with_chatgpt(text: str, genes: list, model="gpt-3.5-turbo") -> dict:
    """
    Fragt ChatGPT:
      - Welche Gene aus 'genes' finden sich thematisch im Text wieder?
    
    Gibt ein Dict zurück: { "GenA": True/False, "GenB": True/False, ... }.
    True = "Yes", False = "No"
    """
    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        st.warning("Kein OPENAI_API_KEY in st.secrets['OPENAI_API_KEY'] hinterlegt!")
        return {}

    if not text.strip():
        st.warning("Kein Text eingegeben.")
        return {}

    if not genes:
        st.info("Keine Gene in der Liste (Sheet möglicherweise leer?).")
        return {}

    # Prompt zusammenbauen
    joined_genes = ", ".join(genes)
    prompt = (
        f"Hier ist ein Text:\n\n{text}\n\n"
        f"Hier eine Liste von Genen: {joined_genes}\n"
        f"Gib für jedes Gen an, ob es im Text vorkommt (Yes) oder nicht (No).\n"
        f"Antworte zeilenweise in der Form:\n"
        f"GENE: Yes\nGENE2: No\n"
    )

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0
        )
        answer = response.choices[0].message.content.strip()

        result_map = {}
        for line in answer.split("\n"):
            line = line.strip()
            if ":" in line:
                parts = line.split(":", 1)
                gene_name = parts[0].strip()
                yes_no = parts[1].strip().lower()
                result_map[gene_name] = ("yes" in yes_no)
        return result_map

    except Exception as e:
        st.error(f"ChatGPT Fehler: {e}")
        return {}

##############################################################################
# 4) Haupt-Funktion für Streamlit
##############################################################################

def module_online_api_filter():
    """
    Zeigt ein Dropdown (Selectbox) für die Sheets in 'genes.xlsx', lädt
    Gene ab C3 und filtert via ChatGPT, ob diese Gene im eingegebenen
    Text erwähnt werden.
    """
    st.title("Gene-Filter (ab C3) mit ChatGPT")

    # Prüfen, ob 'genes.xlsx' in modules/ existiert
    excel_path = os.path.join("modules", "genes.xlsx")
    if not os.path.exists(excel_path):
        st.error("Die Datei 'genes.xlsx' wurde nicht in 'modules/' gefunden!")
        return

    # Sheets ermitteln
    try:
        xls = pd.ExcelFile(excel_path)
        sheet_names = xls.sheet_names
    except Exception as e:
        st.error(f"Fehler beim Öffnen von genes.xlsx: {e}")
        return

    if not sheet_names:
        st.error("Keine Sheets in genes.xlsx gefunden.")
        return

    # Sheet auswählen
    sheet_choice = st.selectbox("Wähle ein Sheet in genes.xlsx:", sheet_names)

    # Falls ein Sheet gewählt wurde, Gene laden
    genes = []
    if sheet_choice:
        genes = load_genes_from_excel(sheet_choice)
        st.write(f"Gelistete Gene in Sheet '{sheet_choice}' (ab C3):")
        st.write(genes)

    st.write("---")
    st.subheader("Text eingeben (z. B. Abstract, Paper-Abschnitt)")

    text_input = st.text_area("Füge hier deinen Abstract / Text ein:", height=200)

    if st.button("Gene filtern mit ChatGPT"):
        if not genes:
            st.warning("Keine Gene geladen oder das gewählte Sheet ist leer.")
            return
        if not text_input.strip():
            st.warning("Bitte einen Text eingeben.")
            return

        result_map = check_genes_in_text_with_chatgpt(text_input, genes)
        if not result_map:
            st.info("Keine Ergebnisse oder es ist ein Fehler aufgetreten.")
            return

        st.markdown("### Ergebnis:")
        for g in genes:
            found = result_map.get(g, False)
            if found:
                st.write(f"**{g}**: YES")
            else:
                st.write(f"{g}: No")

    st.write("---")
    st.info("Fertig. Die Gene wurden ab C3 eingelesen. Du kannst weitere Sheets auswählen oder neue Texte eingeben.")
