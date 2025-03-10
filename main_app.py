import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO
import re
import datetime

# Importing necessary modules
from modules.online_api_filter import module_online_api_filter
from modules.paperqa2_module import module_paperqa2  # <-- ADDED HERE

st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

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
    }
    for label, page in pages.items():
        if st.sidebar.button(label, key=label):
            st.session_state["current_page"] = label
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "Home"
    return pages[st.session_state["current_page"]]

################################################################################
# 7) PaperQA2 Integration
################################################################################

def page_paperqa2():
    st.title("PaperQA2")
    module_paperqa2()  # Calling the module from modules.paperqa2_module
    if st.button("Back to Main Menu"):
        st.session_state["current_page"] = "Home"

################################################################################
# Main Execution
################################################################################

def main():
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
