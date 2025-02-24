# main_app.py
import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO

# Hier importieren wir das neue Modul, in dem page_api_selection liegt:
import api_select

st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

############################
# Beispiel-Seitenfunktionen
############################
def page_home():
    st.title("Welcome to the Main Menu")
    st.write("Choose a module in the sidebar to proceed.")

def page_online_filter():
    st.title("Online Filter Settings")
    st.write("Configure your online filter here. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_codewords_pubmed():
    st.title("Codewords & PubMed Settings")
    st.write("Configure codewords, synonyms, etc. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_paper_selection():
    st.title("Paper Selection Settings")
    st.write("Define how you want to pick or exclude certain papers. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_analysis():
    st.title("Analysis & Evaluation Settings")
    st.write("Set up your analysis parameters, thresholds, etc. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_extended_topics():
    st.title("Extended Topics")
    st.write("Access advanced or extended topics for further research. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

#############################################
# Sidebar Module Navigation
#############################################
def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")

    # Wir bauen ein Dictionary, in dem die Namen
    # den zugehörigen Seitenfunktionen zugeordnet werden:
    pages = {
        "Home": page_home,
        # 1) API Selection: Kommt jetzt AUS api_select.py
        "1) API Selection": api_select.page_api_selection,
        "2) Online Filter": page_online_filter,
        "3) Codewords & PubMed": page_codewords_pubmed,
        "4) Paper Selection": page_paper_selection,
        "5) Analysis & Evaluation": page_analysis,
        "6) Extended Topics": page_extended_topics
    }

    for label in pages.keys():
        if st.sidebar.button(label):
            st.session_state["current_page"] = label

    # Falls man noch nie geklickt hat, Startseite 'Home'
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"

    # Gib die aktuell gewählte Seitenfunktion zurück
    return pages[st.session_state["current_page"]]

#############################################
# Main Streamlit App
#############################################
def main():
    # Ggf. CSS-Anpassungen
    st.markdown(
        """
        <style>
        html, body {
            margin: 0;
            padding: 0;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Bestimme, welche Seite gerendert wird
    page_fn = sidebar_module_navigation()
    page_fn()

if __name__ == '__main__':
    main()
