import streamlit as st

def page_api_selection():
    """
    Zeigt eine Liste von APIs als Checkboxen an. 
    Ausgewählte APIs werden rot markiert. 
    Darunter befindet sich ein grüner Button ("Confirm selection"), 
    um die Auswahl zu übernehmen. 
    Via "Back to Main Menu" kann man wieder zur Startseite zurückkehren.
    """

    st.title("API Selection & Connection Status")

    # CSS, um den Confirm-Button grün zu machen
    st.markdown(
        """
        <style>
        div.stButton > button:first-child {
            background-color: green;
            color: white;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Liste der möglichen APIs
    all_apis = [
        "Europe PMC",
        "PubMed",
        "CORE Aggregate",
        "OpenAlex",
        "Google Scholar",
        "Semantic Scholar"
    ]

    # Standard-Auswahl, falls noch nicht vorhanden
    if "selected_apis" not in st.session_state:
        st.session_state["selected_apis"] = ["Europe PMC"]

    # Temporäre Datenstruktur für Checkbox-Zustände
    selected_apis_temp = set(st.session_state["selected_apis"])

    st.write("Bitte wähle eine oder mehrere der folgenden APIs:")

    # Für jede API eine Checkbox + roter Hinweis, falls ausgewählt
    for api in all_apis:
        is_checked = (api in selected_apis_temp)
        checked = st.checkbox(api, value=is_checked, key="chk_"+api)

        # Rot markiertes Label, falls angehakt
        if checked:
            st.markdown(
                f"<div style='background-color:red; color:white; padding:4px; margin-bottom:8px;'>"
                f"{api} is selected</div>",
                unsafe_allow_html=True
            )
        else:
            st.write(f"{api} is not selected")

    st.write("---")

    # Grüner Button zum Bestätigen der Auswahl
    if st.button("Confirm selection"):
        # Ausgelesene Zustände in st.session_state["selected_apis"] übernehmen
        new_list = []
        for api in all_apis:
            if st.session_state.get("chk_"+api, False):
                new_list.append(api)
        st.session_state["selected_apis"] = new_list
        st.success(f"API selection updated: {new_list}")

    # Button für Rückkehr ins Hauptmenü
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"
