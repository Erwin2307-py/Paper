# main.py

import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO

# Hier importieren wir unser externes Modul api_select
import api_select

st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")


#############################
# Hier könnten weiterhin deine
# Check-Funktionen, Search-Funktionen usw. stehen,
# sofern sie nicht in api_select.py ausgelagert wurden.
#############################


#############################
# Beispiel-Seiten (Pages)
#############################

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


#############################
# Sidebar Module Navigation
#############################
def sidebar_module_navigation():
    """
    Zeichnet die Module in der Sidebar. Je nach Button-Klick wird
    st.session_state["current_page"] auf den zugehörigen Wert gesetzt.
    """
    st.sidebar.title("Module Navigation")

    # Wir legen ein Dict an, das den Namen der Seite
    # auf die entsprechende Funktion mappt.
    pages = {
        "Home": page_home,
        # HIER binden wir unsere page_api_selection aus api_select ein
        "1) API Selection": api_select.page_api_selection,
        "2) Online Filter": page_online_filter,
        "3) Codewords & PubMed": page_codewords_pubmed,
        "4) Paper Selection": page_paper_selection,
        "5) Analysis & Evaluation": page_analysis,
        "6) Extended Topics": page_extended_topics
    }
    
    # Für jedes Label (Schlüssel) machen wir einen Button
    for label in pages.keys():
        if st.sidebar.button(label):
            st.session_state["current_page"] = label

    # Falls "current_page" noch nicht definiert ist, setzen wir sie auf "Home"
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"
    
    # pages[...] gibt die Funktion zurück, die gerendert werden soll
    return pages[st.session_state["current_page"]]


#############################
# Haupt-App
#############################
def main():
    # Wir fügen etwas CSS hinzu, wenn nötig
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

    # 1) Modul-Navigation im Sidebar
    page_fn = sidebar_module_navigation()

    # 2) Rufe die aktuelle Page-Funktion auf
    page_fn()


#############################
# Start
#############################
if __name__ == '__main__':
    main()

