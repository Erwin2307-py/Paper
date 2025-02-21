import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from io import BytesIO

# Must be the very first Streamlit command!
st.set_page_config(page_title="Streamlit Multi-Module Demo", layout="wide")

# Inject custom CSS to remove default margins and paddings so the green bar is flush.
st.markdown(
    """
    <style>
    html, body {
        margin: 0;
        padding: 0;
    }
    /* Force sidebar buttons to be full width and equally sized */
    div[data-testid="stSidebar"] button {
         width: 100% !important;
         margin: 0px !important;
         padding: 10px !important;
         font-size: 16px !important;
         text-align: center !important;
         box-sizing: border-box;
    }
    </style>
    """,
    unsafe_allow_html=True
)

#############################################
# PubMed Connection Check
#############################################
def check_pubmed_connection(timeout=10):
    """Kurzer Test, ob PubMed erreichbar ist."""
    test_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": "test", "retmode": "json"}
    try:
        r = requests.get(test_url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return "esearchresult" in data
    except Exception:
        return False

#############################################
# PubMed Search Function
#############################################
def search_pubmed(query):
    """
    Führt eine PubMed-Suche durch und gibt eine Liste von Dicts zurück:
    [
      {
        "PMID": "12345678",
        "Title": "Ein Titel",
        "Year": "2021",
        "Journal": "Nature"
      },
      ...
    ]
    """
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 100}
    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            return []

        # eSummary aufrufen, um Jahr/Journal herauszubekommen
        esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        sum_params = {"db": "pubmed", "id": ",".join(idlist), "retmode": "json"}
        resp_sum = requests.get(esummary_url, params=sum_params, timeout=10)
        resp_sum.raise_for_status()
        summary_data = resp_sum.json().get("result", {})

        results = []
        for pmid in idlist:
            info = summary_data.get(pmid, {})
            title = info.get("title", "n/a")
            pubdate = info.get("pubdate", "")
            # Jahr (z.B. "2021 Dec") -> "2021"
            year = pubdate[:4] if pubdate else "n/a"
            journal = info.get("fulljournalname", "n/a")

            results.append({
                "PMID": pmid,
                "Title": title,
                "Year": year,
                "Journal": journal
            })
        return results

    except Exception as e:
        st.error(f"Error searching PubMed: {e}")
        return []

#############################################
# PubMed Abstract Fetch
#############################################
def fetch_pubmed_abstract(pmid):
    """Holt das Abstract zu einer PubMed-ID via eFetch."""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        abs_text = []
        for elem in root.findall(".//AbstractText"):
            if elem.text:
                abs_text.append(elem.text.strip())
        if abs_text:
            return "\n".join(abs_text)
        else:
            return "(No abstract available)"
    except Exception as e:
        return f"(Error fetching abstract: {e})"

#############################################
# Excel Export
#############################################
def convert_to_excel(data):
    """
    Erwartet eine Liste von Dicts, z.B.:
    [
      {
        "PMID": "12345",
        "Title": "Beispieltitel",
        "Year": "2020",
        "Journal": "Nature",
        "Abstract": "...",
      },
      ...
    ]
    und gibt ein BytesIO-Objekt für den Download zurück.
    """
    import pandas as pd
    from io import BytesIO

    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="PubMed")
        # Keine writer.save() mehr nötig (Kontextmanager schließt die Datei)
    return output.getvalue()

#############################################
# GUI: Top Green Bar
#############################################
def top_green_bar():
    st.markdown(
        """
        <div style="
            background-color: #8BC34A;
            width: 100vw;
            height: 3cm;
            margin: 0;
            padding: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            position: fixed;
            top: 0;
            left: 0;
            z-index: 1000;">
        """,
        unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)

#############################################
# Main Streamlit App
#############################################
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

    # Oberer grüner Balken (statisch)    
    top_green_bar()

    # Platz schaffen, damit der Content nicht hinter dem Balken verschwindet
    st.markdown("<div style='padding-top: 3.2cm;'></div>", unsafe_allow_html=True)
    
    st.title("PubMed Multi-Selection with Excel Download")

    # Session State anlegen (falls nicht existiert)
    if "pubmed_results" not in st.session_state:
        st.session_state["pubmed_results"] = []
    if "selected_papers" not in st.session_state:
        st.session_state["selected_papers"] = []

    st.subheader("Search PubMed")
    query = st.text_input("Enter a search query:", "")
    
    if st.button("Search"):
        if not query.strip():
            st.warning("Please enter a search query.")
        else:
            hits = search_pubmed(query)
            st.session_state["pubmed_results"] = hits
            st.write(f"Found {len(hits)} paper(s).")

    # Ergebnisse anzeigen, wenn vorhanden
    if st.session_state["pubmed_results"]:
        st.table(st.session_state["pubmed_results"])
        
        # Multiselect
        paper_options = [
            f"{p['Title']} (PMID: {p['PMID']})"
            for p in st.session_state["pubmed_results"]
        ]
        selected_now = st.multiselect(
            "Select paper(s) to view abstracts:",
            options=paper_options,
            default=st.session_state["selected_papers"],
            key="paper_multiselect"
        )
        st.session_state["selected_papers"] = selected_now

        # Für Download
        selected_details = []

        # Für jedes ausgewählte Paper -> Abstract anzeigen
        for item in st.session_state["selected_papers"]:
            try:
                pmid = item.split("PMID: ")[1].rstrip(")")
            except IndexError:
                pmid = ""
            if pmid:
                # Aus den Suchergebnissen Meta-Daten holen
                meta = next((x for x in st.session_state["pubmed_results"] if x["PMID"] == pmid), {})
                abstract_text = fetch_pubmed_abstract(pmid)
                
                st.subheader(f"Abstract for PMID {pmid}")
                st.write(f"**Title:** {meta.get('Title', 'n/a')}")
                st.write(f"**Year:** {meta.get('Year', 'n/a')}")
                st.write(f"**Journal:** {meta.get('Journal', 'n/a')}")
                st.write("**Abstract:**")
                st.write(abstract_text)

                # Sammeln für Excel
                selected_details.append({
                    "PMID": pmid,
                    "Title": meta.get("Title", "n/a"),
                    "Year": meta.get("Year", "n/a"),
                    "Journal": meta.get("Journal", "n/a"),
                    "Abstract": abstract_text
                })

        # Download-Button für die aktuell ausgewählten Paper
        if selected_details:
            excel_bytes = convert_to_excel(selected_details)
            st.download_button(
                label="Download selected papers as Excel",
                data=excel_bytes,
                file_name="Selected_Papers.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.info("No results yet. Please enter a query and click 'Search'.")

if __name__ == "__main__":
    main()
