import streamlit as st
import requests
import openai
import pandas as pd
import os

##############################################################################
# 1) ChatGPT-Verbindungscheck (wenn gewünscht)
##############################################################################

def check_chatgpt_connection():
    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        return False
    try:
        openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"user", "content":"Short connectivity test. Reply with any short message."}],
            max_tokens=10,
            temperature=0
        )
        return True
    except Exception:
        return False

##############################################################################
# 2) Gene-Loader: Liest ab C3 einer gegebenen Sheet
##############################################################################

def load_genes_from_excel(sheet_name: str) -> list:
    """
    Lädt die Gene ab Zelle C3 (Spalte C, Zeile 3) aus dem gewählten Sheet in `modules/genes.xlsx`.
    Wir nehmen an, dass:
    - 'genes.xlsx' direkt im Ordner 'modules' liegt.
    - In Spalte C ab Zeile 3 stehen die Gen-Namen. (Also df.iloc[2:, 2])
    """
    excel_path = os.path.join("modules", "genes.xlsx")
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)

        # df.iloc[row, col] => row=2 => ab Zeile 3, col=2 => Spalte C
        gene_series = df.iloc[2:, 2]  # ab Zeile 3 (Index=2), Spalte 3 (Index=2)

        # NaN rauswerfen + in string umwandeln
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
    Fragt ChatGPT: Welche Gene aus 'genes' sind im Text thematisch erwähnt/relevant?
    Gibt ein dict zurück: {Gen1: True, Gen2: False, ...}
    """
    openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not openai.api_key:
        st.warning("Kein OPENAI_API_KEY in st.secrets['OPENAI_API_KEY'] hinterlegt!")
        return {}

    if not text.strip():
        st.warning("Kein Text eingegeben.")
        return {}

    if not genes:
        st.info("Keine Gene in der Liste (Sheet leer?).")
        return {}

    # Prompt bauen
    joined_genes = ", ".join(genes)
    prompt = (
        f"Hier ist ein Text:\n\n{text}\n\n"
        f"Hier eine Liste von Genen: {joined_genes}\n"
        f"Gib für jedes Gen an, ob es im Text vorkommt (Yes) oder nicht (No).\n"
        f"Antworte in Zeilen der Form:\n"
        f\"\"\"GENE: Yes\nGENE2: No\"\"\"\n"
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
    Zeigt ein Dropdown (Selectbox) für die Sheets, lädt die Gene ab C3 und filtert
    via ChatGPT, ob die Gene im eingegebenen Text erwähnt sind.
    """
    st.title("Gene-Filter (ab C3) mit ChatGPT")

    # A) Check: Liegt die Excel vor?
    excel_path = os.path.join("modules", "genes.xlsx")
    if not os.path.exists(excel_path):
        st.error("Die Datei 'genes.xlsx' wurde nicht in 'modules/' gefunden!")
        return

    # B) Sheets per Pandas abfragen
    try:
        xls = pd.ExcelFile(excel_path)
        sheet_names = xls.sheet_names
    except Exception as e:
        st.error(f"Fehler beim Öffnen von genes.xlsx: {e}")
        return

    if not sheet_names:
        st.error("Keine Sheets gefunden in genes.xlsx.")
        return

    # Sheet Dropdown
    sheet_choice = st.selectbox("Wähle ein Sheet in genes.xlsx:", sheet_names)

    # Gene laden
    genes = []
    if sheet_choice:
        genes = load_genes_from_excel(sheet_choice)
        st.write(f"Gelistete Gene in Sheet '{sheet_choice}' (ab C3):")
        st.write(genes)

    st.markdown("---")
    st.subheader("Text eingeben (z. B. Abstract, Paper)")

    text_input = st.text_area("Füge hier deinen Abstract / Text ein:", height=200)

    if st.button("Gene filtern mit ChatGPT"):
        if not genes:
            st.warning("Keine Gene geladen oder Sheet leer.")
            return
        if not text_input.strip():
            st.warning("Bitte einen Text eingeben.")
            return

        result_map = check_genes_in_text_with_chatgpt(text_input, genes)
        if not result_map:
            st.info("Keine Ergebnisse oder Fehler aufgetreten.")
            return

        st.markdown("### Ergebnis:")
        for g in genes:
            found = result_map.get(g, False)
            if found:
                st.write(f"**{g}**: YES")
            else:
                st.write(f"{g}: No")

    st.markdown("---")
    st.info("Fertig. Die Gene wurden ab C3 eingelesen. Du kannst weitere Sheets auswählen oder neue Texte eingeben.")
