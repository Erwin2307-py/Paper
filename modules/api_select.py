import streamlit as st

def module_api_select():
    st.header("Modul 1: Wähle APIs aus")

    # Wir nutzen einen Multi-Select:
    options = ["Europe PMC", "PubMed", "OpenAlex", "Google Scholar", "Semantic Scholar", "CORE Aggregate"]
    selected_apis = st.multiselect("Welche APIs möchtest du nutzen?", options, default=["Europe PMC"])

    st.session_state["selected_apis"] = selected_apis

    st.write("Aktuell ausgewählt:", selected_apis)
