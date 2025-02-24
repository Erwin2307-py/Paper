import streamlit as st
import modul_a
import modul_b

def main():
    # Seitentitel
    st.title("Meine Streamlit App")

    # Sidebar-Titel
    st.sidebar.title("Navigation")

    # Buttons in der Sidebar
    if st.sidebar.button("Modul A öffnen"):
        st.session_state["aktuelles_modul"] = "A"
    if st.sidebar.button("Modul B öffnen"):
        st.session_state["aktuelles_modul"] = "B"

    # Abfrage, welches Modul gerade ausgewählt wurde
    if "aktuelles_modul" not in st.session_state:
        st.write("Wähle ein Modul in der Sidebar aus, um zu starten.")
    else:
        # Je nach ausgewähltem Modul die passende Funktion aufrufen
        if st.session_state["aktuelles_modul"] == "A":
            modul_a.fenster_oeffnen()
        elif st.session_state["aktuelles_modul"] == "B":
            modul_b.fenster_oeffnen()

if __name__ == "__main__":
    # Damit nur ausgeführt wird, wenn dieses Skript direkt gestartet wird
    main()


