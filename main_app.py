import streamlit as st

# Our module imports:
from modules.api_select import module_api_select
from modules.online_filter import module_online_filter
from modules.codewords_pubmed import module_codewords_pubmed
from modules.paper_select_remove import module_select_remove
from modules.analysis import module_analysis
from modules.extended_topics import module_extended_topics

def main():
    st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

    # --- Top Green Bar --- 
    st.markdown(
        """
        <div style='background-color: #8BC34A; padding: 15px; text-align: center; color: white; font-size: 28px; font-weight: bold;'>
            Streamlit Multi-Modul Demo
        </div>
        """,
        unsafe_allow_html=True
    )

    # --- CSS for green sidebar ---
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

    # Sidebar Module Navigation (persistent)
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

    # Module call depending on selection
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

if __name__ == "__main__":
    main()

    main()
