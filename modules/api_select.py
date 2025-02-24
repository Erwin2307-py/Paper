import streamlit as st

def page_api_selection():
    """
    Zeigt eine Liste von APIs als Checkboxen an (kein Dropdown).
    Ausgewählte APIs werden rot markiert.
    Darunter befindet sich ein grüner Button ("Confirm selection"),
    um die Auswahl zu übernehmen.
    Und es gibt einen "Back to Main Menu"-Button.
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

    # Liste der verfügbaren APIs
    all_apis = [
        "Europe PMC",
        "PubMed",
        "CORE Aggregate",
        "OpenAlex",
        "Google Scholar",
        "Semantic Scholar"
    ]

    # Falls noch kein Eintrag in Session State
    if "selected_apis" not in st.session_state:
        st.session_state["selected_apis"] = ["Europe PMC"]  # Standard

    # Temporäre Struktur, um Checkbox-Zustände zu definieren
    # (zunächst basierend auf dem, was wir in selected_apis haben)
    selected_apis_temp = set(st.session_state["selected_apis"])

    st.write("Wähle deine APIs durch Anklicken der Kästchen:")

    # Für jede API eine Checkbox
    # Wenn angehakt, roter Hinweis
    for api in all_apis:
        is_checked = (api in selected_apis_temp)

        # Eindeutiger Key pro Checkbox
        cb_state = st.checkbox(api, value=is_checked, key="chk_"+api)

        # Wenn Checkbox angehakt, roter Block
        if cb_state:
            st.markdown(
                f"<div style='background-color:red; color:white; padding:4px; margin-bottom:8px;'>"
                f"{api} is selected</div>",
                unsafe_allow_html=True
            )
        else:
            st.write(f"{api} is not selected")

    st.write("---")

    # Grüner Bestätigungs-Button
    if st.button("Confirm selection"):
        # Baue eine neue Liste auf Grundlage der Checkbox-Zustände
        new_list = []
        for api in all_apis:
            # Falls die Checkbox "chk_"+api True ist
            if st.session_state.get("chk_"+api, False):
                new_list.append(api)
        st.session_state["selected_apis"] = new_list
        st.success(f"API selection updated: {new_list}")

    # Zurück-Button
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

