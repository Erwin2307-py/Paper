import streamlit as st

# Importe weiterer benötigter Funktionen
# (hier musst du ggf. anpassen, falls du bestimmte Funktionen aus app.py
#  oder anderen Modulen importieren möchtest)
from app import (
    check_pubmed_connection,
    check_europe_pmc_connection,
    check_core_aggregate_connection
)

def page_api_selection():
    st.title("API Selection & Connection Status")
    st.write("Auf dieser Seite kannst du die zu verwendenden APIs wählen und den Verbindungsstatus prüfen.")
    
    # Beispiel-Liste aller möglichen APIs
    all_apis = [
        "Europe PMC",
        "PubMed",
        "CORE Aggregate",
        "OpenAlex",
        "Google Scholar",
        "Semantic Scholar"
    ]
    
    # Session State für die Auswahl der APIs initialisieren
    if "selected_apis" not in st.session_state:
        st.session_state["selected_apis"] = ["Europe PMC"]

    chosen_apis = st.multiselect(
        "Select APIs to use:",
        all_apis,
        default=st.session_state["selected_apis"]
    )
    st.session_state["selected_apis"] = chosen_apis
    st.write("Currently selected APIs:", chosen_apis)

    # Verbindungstest
    st.subheader("Connection Tests")
    msgs = []
    
    if "PubMed" in chosen_apis:
        if check_pubmed_connection():
            msgs.append("PubMed: OK")
        else:
            msgs.append("PubMed: FAIL")
            
    if "Europe PMC" in chosen_apis:
        if check_europe_pmc_connection():
            msgs.append("Europe PMC: OK")
        else:
            msgs.append("Europe PMC: FAIL")
    
    if "CORE Aggregate" in chosen_apis:
        core_key = st.secrets.get("CORE_API_KEY", "")
        if core_key and check_core_aggregate_connection(core_key):
            msgs.append("CORE: OK")
        else:
            msgs.append("CORE: FAIL (No valid key or no connection)")

    if msgs:
        for m in msgs:
            st.write("- ", m)
    else:
        st.write("No APIs selected or no checks performed.")

    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"
