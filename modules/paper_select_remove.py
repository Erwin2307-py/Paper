import streamlit as st

def module_select_remove():
    """
    Zeigt eine Liste von Papers (in st.session_state["paper_list"])
    und ermöglicht Sortieren, Filtern und Verschieben in "Favoriten".
    """
    st.header("Modul: Paper auswählen oder entfernen (mit Sortierung & Filter)")

    # 1) Falls keine paper_list in session_state vorhanden, legen wir ein paar Dummies an:
    if "paper_list" not in st.session_state:
        st.session_state["paper_list"] = [
            {
                "Title": "Paper A",
                "PubMed ID": "12345",
                "Year": 2021,
                "Publisher": "Nature",
                "Source": "PubMed"
            },
            {
                "Title": "Paper B",
                "PubMed ID": "99999",
                "Year": 2022,
                "Publisher": "Science",
                "Source": "Google Scholar"
            },
            {
                "Title": "Paper C",
                "PubMed ID": "77777",
                "Year": 2020,
                "Publisher": "Elsevier",
                "Source": "Europe PMC"
            },
            {
                "Title": "Paper D",
                "PubMed ID": "55555",
                "Year": 2021,
                "Publisher": "Science",
                "Source": "OpenAlex"
            },
        ]

    # 2) Filter-Funktion (z. B. nach Jahr)
    all_years = sorted({p.get("Year", "n/a") for p in st.session_state["paper_list"]})
    year_filter = st.selectbox("Filter nach Jahr:", ["Alle"] + [str(y) for y in all_years], index=0)

    if year_filter != "Alle":
        paper_list_filtered = [p for p in st.session_state["paper_list"] if str(p.get("Year", "")) == year_filter]
    else:
        paper_list_filtered = st.session_state["paper_list"]

    # 3) Sortier-Optionen
    sort_fields = ["Year", "Publisher", "PubMed ID", "Source"]
    sort_choice = st.selectbox("Sortiere gefundene Paper nach:", sort_fields, index=0)
    st.write("Sortiere nach:", sort_choice)

    def sort_key_func(p):
        return p.get(sort_choice, "")

    paper_list_sorted = sorted(paper_list_filtered, key=sort_key_func)

    # -> Kolumnen: links, rechts
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Gefundene Paper (Links)")

        # Wir nehmen den Title als identifier
        all_titles_sorted = [p["Title"] for p in paper_list_sorted]

        selected_left = st.multiselect(
            "Wähle aus, welche Paper du übernehmen möchtest:",
            options=all_titles_sorted
        )

        if st.button("Ausgewählte -> Favoriten hinzufügen"):
            if "selected_papers" not in st.session_state:
                st.session_state["selected_papers"] = []
            for title in selected_left:
                if title not in st.session_state["selected_papers"]:
                    st.session_state["selected_papers"].append(title)
            st.success(f"Folgende Paper wurden hinzugefügt: {selected_left}")

    with col_right:
        st.subheader("Favoriten (Rechts)")
        current_favs = st.session_state.get("selected_papers", [])
        if not current_favs:
            st.info("Noch keine Favoriten ausgewählt.")
        else:
            st.write("Aktuelle Favoriten:", current_favs)

            remove_list = st.multiselect("Favoriten entfernen:", current_favs)
            if st.button("Entfernen"):
                st.session_state["selected_papers"] = [
                    p for p in current_favs if p not in remove_list
                ]
                st.success(f"'{remove_list}' entfernt.")


# Wenn dieses Skript direkt ausgeführt wird:
if __name__ == "__main__":
    st.set_page_config(layout="wide")
    module_select_remove()
