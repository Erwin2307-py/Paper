# main.py

import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO

# Hier importieren wir das externe Modul:
import api_select

st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

#############################################
# Beispiel: Deine Checks & Logic
#############################################

def page_home():
    st.title("Welcome to the Main Menu")
    st.write("Choose a module in the sidebar to proceed.")
    st.write("Hier könnte dein Haupt-Inhalt stehen, bis man sich für ein anderes Modul entscheidet.")

def page_online_filter():
    st.title("Online Filter Settings")
    st.write("Configure your online filter here. (Dummy placeholder...)")
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_codewords_pubmed():
    st.title("Codewords & PubMed Settings")
    st.write("Configure codewords, synonyms, etc. for your PubMed search. (Dummy placeholder...)")
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

def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")
    
    # Wir bauen ein Dict, in dem wir die Namen den Funktionen zuordnen
    pages = {
        "Home": page_home,
        # API Selection verweist auf die Funktion in api_select.py
        "1) API Selection": api_select.page_api_selection,
        "2) Online Filter": page_online_filter,
        "3) Codewords & PubMed": page_codewords_pubmed,
        "4) Paper Selection": page_paper_selection,
        "5) Analysis & Evaluation": page_analysis,
        "6) Extended Topics": page_extended_topics
    }
    
    # Sidebar Buttons
    for label in pages.keys():
        if st.sidebar.button(label):
            st.session_state["current_page"] = label

    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"
    
    # Return the function that was selected
    return pages[st.session_state["current_page"]]

def main():
    # Ein bisschen CSS
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

    # Navigation
    page_fn = sidebar_module_navigation()
    # Rendering der gewählten Seite
    page_fn()

if __name__ == '__main__':
    main()
