import streamlit as st
import requests

# Must be the first Streamlit command!
st.set_page_config(page_title="Streamlit Multi-Modul Demo", layout="wide")

# Inject custom CSS to remove default body margins and create a fixed green bar at the top.
st.markdown(
    """
    <style>
    /* Remove default margins and padding */
    html, body {
        margin: 0;
        padding: 0;
    }
    /* Remove any additional container margins (Streamlit's default containers) */
    .css-18e3th9, .css-1d391kg {
        margin: 0;
        padding: 0;
    }
    /* Create a fixed top green bar that spans full width */
    .top-green-bar {
        background-color: #8BC34A;
        width: 100vw;
        height: 3cm;
        position: fixed;
        top: 0;
        left: 0;
        z-index: 1000;
    }
    /* Push the main content down so it doesn't get hidden behind the green bar */
    .main-content {
        padding-top: 3cm;
    }
    </style>
    <div class="top-green-bar"></div>
    """,
    unsafe_allow_html=True
)

# Our module imports (adjust paths as needed)
from modules.api_select import module_api_select
from modules.online_filter import module_online_filter
from modules.codewords_pubmed import module_codewords_pubmed
from modules.paper_select_remove import module_select_remove
from modules.analysis import module_analysis
from modules.extended_topics import module_extended_topics

def main():
    # Wrap main content in a div to apply top padding
    st.markdown('<div class="main-content">', unsafe_allow_html=True)
    
    st.title("API Connection Checker")
    
    # Always display the API selection sidebar so that the choices remain visible
    module_api_select()
    
    st.write("This app checks API connections and provides several modules for further processing.")
    st.write("Use the sidebar to navigate between modules. The top green bar remains fixed at the top.")
    
    st.markdown("</div>", unsafe_allow_html=True)  # End main-content div

if __name__ == '__main__':
    main()
