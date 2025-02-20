import streamlit as st

def module_select_remove():
    st.header("Modul 4: Paper auswählen oder entfernen")

    # Beispiel: Wir gehen davon aus, dass st.session_state["paper_list"] existiert
    if "paper_list" not in st.session_state:
        st.session_state["paper_list"] = [
            {"Title": "Paper A", "Author": "Autor 1", "Year": 2021},
            {"Title": "Paper B", "Author": "Autor 2", "Year": 2022},
        ]

    # Zeige Liste
    all_titles = [p["Title"] for p in st.session_state["paper_list"]]
    selected = st.multiselect("Wähle Paper aus:", all_titles)

    # Button "Ausgewählt -> session_state"
    if st.button("Zu den Favoriten hinzufügen"):
        if "selected_papers" not in st.session_state:
            st.session_state["selected_papers"] = []
        for t in selected:
            if t not in st.session_state["selected_papers"]:
                st.session_state["selected_papers"].append(t)
        st.success(f"'{selected}' hinzugefügt.")

    st.write("Favoriten (bereits ausgewählt):", st.session_state.get("selected_papers", []))

    # Entfernen
    remove_list = st.multiselect("Favoriten entfernen:", st.session_state.get("selected_papers", []))
    if st.button("Entfernen"):
        st.session_state["selected_papers"] = [p for p in st.session_state["selected_papers"] if p not in remove_list]
        st.success(f"'{remove_list}' entfernt.")
