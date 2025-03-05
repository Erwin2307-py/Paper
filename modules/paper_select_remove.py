import streamlit as st

def module_select_remove():
    st.header("Modul 4: Paper auswählen oder entfernen (mit Sortierung)")

    # Beispiel: Falls keine paper_list in session_state vorhanden, legen wir ein paar Dummies an:
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
        ]

    # Hier definieren wir mögliche Sortier-Optionen.
    # Du kannst beliebig viele Felder anbieten; wir nehmen hier mal Year, Publisher, PubMed ID, Source
    sort_fields = ["Year", "Publisher", "PubMed ID", "Source"]
    sort_choice = st.selectbox("Sortiere gefundene Paper nach:", sort_fields, index=0)
    st.write("Sortiere nach:", sort_choice)

    # Jetzt sortieren wir die Liste anhand des ausgewählten Feldes
    # (Falls ein Feld fehlt, verwenden wir als Fallback "")
    def sort_key_func(p):
        return p.get(sort_choice, "")

    paper_list_sorted = sorted(st.session_state["paper_list"], key=sort_key_func)

    # Spalte links: Gefundene Paper
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Gefundene Paper (Links)")
        # Für die Multiselect brauchen wir einen "unique identifier" – hier den "Title"
        # Du könntest natürlich z.B. (Title + PubMed ID) verknüpfen, wenn es Dublikate geben kann.
        all_titles_sorted = [p["Title"] for p in paper_list_sorted]

        selected_left = st.multiselect(
            "Wähle aus, welche Paper du übernehmen möchtest:",
            options=all_titles_sorted
        )

        if st.button("Ausgewählte -> Favoriten hinzufügen"):
            # Falls wir in session_state noch keine "selected_papers" haben, legen wir sie an
            if "selected_papers" not in st.session_state:
                st.session_state["selected_papers"] = []
            # Jeden Titel, der noch nicht in selected_papers ist, hinzufügen
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

            remove_list = st.multiselect(
                "Favoriten entfernen:",
                current_favs
            )
            if st.button("Entfernen"):
                st.session_state["selected_papers"] = [
                    p for p in current_favs if p not in remove_list
                ]
                st.success(f"'{remove_list}' entfernt.")


# Wenn du das Modul direkt ausführst:
if __name__ == "__main__":
    st.set_page_config(layout="wide")  # optional, um mehr Platz zu haben
    module_select_remove()
