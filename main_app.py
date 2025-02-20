import streamlit as st
import requests

# Must be the first Streamlit command!
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

# Our module imports (adjust paths as needed)
from modules.api_select import module_api_select
from modules.online_filter import module_online_filter
from modules.codewords_pubmed import module_codewords_pubmed
from modules.paper_select_remove import module_select_remove
from modules.analysis import module_analysis
from modules.extended_topics import module_extended_topics

def main():
    # --- Top Green Bar (full width) ---
    # This green bar spans the full width at the top. Adjust padding if needed.
    st.markdown(
        """
        <div style="background-color: #8BC34A; width: 100%; height: 3cm; margin: 0; padding: 0;"></div>
        """,
        unsafe_allow_html=True
    )
    
    # --- Sidebar CSS to keep it green ---
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            background-color: #8BC34A;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    # --- Sidebar Module Navigation (Persistent) ---
    st.sidebar.title("Module Navigation")
    selection = st.sidebar.radio(
        "Wähle ein Modul:",
        (
            "1) API-Auswahl",
            "2) Online-Filter",
            "3) Codewörter & PubMed",
            "4) Paper-Auswahl",
            "5) Analyse & Bewertung",
            "6) Erweiterte Themen"
        )
    )
    
    # Module call based on the user's selection
    if selection.startswith("1"):
        module_api_select()
    elif selection.startswith("2"):
        module_online_filter()
    elif selection.startswith("3"):
        module_codewords_pubmed()
    elif selection.startswith("4"):
        module_select_remove()
    elif selection.startswith("5"):
        module_analysis()
    elif selection.startswith("6"):
        module_extended_topics()
    
    st.write("This app checks API connections and provides several modules for further processing.")
    st.write("Use the sidebar to navigate between modules. The top green bar remains visible at all times.")

if __name__ == '__main__':
    main()
