import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO
import re
import datetime

# -----------------------------
# NEW: Import from paperqa2_module
# -----------------------------
from modules.paperqa2_module import module_paperqa2

# (Your other imports remain the same...)
# from modules.online_api_filter import module_online_api_filter
# from scholarly import scholarly
# etc.

# 1) Gemeinsame Funktionen & Klassen
# (unchanged)...

# 2) Neues Modul: "module_excel_online_search"
# (unchanged)...

################################################################################
# 3) Restliche Module + Seiten (Pages)
################################################################################

# ---------------------------------------------------------------------------
# REMOVE the local placeholder function named "module_paperqa2" 
# to avoid conflicts, because we now import it from paperqa2_module.py
#
# def module_paperqa2():
#     st.subheader("PaperQA2 Module")
#     st.write("Dies ist das PaperQA2 Modul. Hier kannst du weitere Einstellungen...")
#     question = st.text_input("Bitte gib deine Frage ein:")
#     if st.button("Frage absenden"):
#         st.write("Antwort: Dies ist eine Dummy-Antwort:", question)
#
# ---------------------------------------------------------------------------

def page_paperqa2():
    st.title("PaperQA2")
    # Call the imported function from modules/paperqa2_module.py
    module_paperqa2()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

def page_home():
    st.title("Welcome to the Main Menu")
    st.write("Choose a module in the sidebar to proceed.")
    st.image("Bild1.jpg", caption="Willkommen!", use_container_width=False, width=600)

def page_codewords_pubmed():
    st.title("Codewords & PubMed Settings")
    from modules.codewords_pubmed import module_codewords_pubmed
    module_codewords_pubmed()
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

def page_excel_online_search():
    st.title("Excel Online Search")
    # Place your logic calling your combined module here, if desired.
    # Example:
    from modules.online_api_filter import module_online_api_filter
    # module_online_api_filter()
    # ...
    pass

def page_online_api_filter():
    st.title("Online-API_Filter (Kombiniert)")
    st.write("Hier kombinierst du ggf. API-Auswahl und Online-Filter in einem Schritt.")
    from modules.online_api_filter import module_online_api_filter
    module_online_api_filter()
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

################################################################################
# 6) Sidebar Module Navigation & Main
################################################################################

def sidebar_module_navigation():
    st.sidebar.title("Module Navigation")
    pages = {
        "Home": page_home,
        "Online-API_Filter": page_online_api_filter,
        "3) Codewords & PubMed": page_codewords_pubmed,
        "4) Paper Selection": page_paper_selection,
        "5) Analysis & Evaluation": page_analysis,
        "6) Extended Topics": page_extended_topics,
        "7) PaperQA2": page_paperqa2,
        "8) Excel Online Search": page_excel_online_search
        # "9) Selenium Q&A": page_selenium_qa, # commented out
    }
    for label, page in pages.items():
        if st.sidebar.button(label, key=label):
            st.session_state["current_page"] = label
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"
    return pages[st.session_state["current_page"]]

def main():
    # optional styling
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

    page_fn = sidebar_module_navigation()
    page_fn()

if __name__ == '__main__':
    main()
