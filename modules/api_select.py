import os
import re
import time
import requests
import openpyxl
import xml.etree.ElementTree as ET
import streamlit as st
from urllib.parse import urljoin
import openai

# >>> OpenAI-API-Key <<<
openai.api_key = "sk-your-chatgpt-api-key"  # Replace with valid key

##############################################################################
# Klassen (aus deinem Code) - gekürzt auf Kernfunktionalitäten
##############################################################################

class DBSnpAPI:
    def __init__(self, email: str, api_key: str):
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        self.params = {
            "db": "snp",
            "retmode": "xml",
            "email": email,
            "api_key": api_key,
            "tool": "DBSnpPythonClient"
        }
        self.namespace = {'ns': 'https://www.ncbi.nlm.nih.gov/SNP/docsum'}

    def get_snp_info(self, rs_id: str):
        """Sucht Informationen zu einer RS-ID (z.B. rs429358) via NCBI dbSNP."""
        try:
            search_params = {"term": f"{rs_id}[RS]", "retmax": "1"}
            search_response = requests.get(
                f"{self.base_url}esearch.fcgi",
                params={**self.params, **search_params},
                timeout=10
            )
            search_response.raise_for_status()
            search_root = ET.fromstring(search_response.content)
            snp_id = search_root.findtext("IdList/Id")
            if not snp_id:
                return None

            fetch_response = requests.get(
                f"{self.base_url}efetch.fcgi",
                params={**self.params, "id": snp_id},
                timeout=10
            )
            fetch_response.raise_for_status()
            return self.parse_xml(fetch_response.content)

        except Exception as e:
            return None

    def parse_xml(self, xml_content):
        root = ET.fromstring(xml_content)
        snp_info = {}
        doc_summary = root.find(".//ns:DocumentSummary", self.namespace)
        if doc_summary is not None:
            snp_info["rs_id"] = "rs" + doc_summary.findtext('ns:SNP_ID', '', self.namespace)
            snp_info["chromosome"] = doc_summary.findtext("ns:CHR", "", self.namespace)
            snp_info["position"] = doc_summary.findtext("ns:CHRPOS", "", self.namespace)
            snp_info["alleles"] = doc_summary.findtext("ns:SPDI", "", self.namespace)
            clin_sig = doc_summary.findtext("ns:CLINICAL_SIGNIFICANCE", "", self.namespace)
            snp_info["clinical_significance"] = clin_sig.split(",") if clin_sig else []
            snp_info["gene"] = doc_summary.findtext("ns:GENES/ns:GENE_E/ns:NAME", "", self.namespace)

            mafs = []
            for maf in doc_summary.findall(".//ns:MAF", self.namespace):
                study = maf.findtext("ns:STUDY", "", self.namespace)
                freq = maf.findtext("ns:FREQ", "", self.namespace)
                mafs.append(f"{study}: {freq}")
            snp_info["mafs"] = mafs

        return snp_info


class CoreAPI:
    """CORE Aggregate-Suche."""
    def __init__(self, api_key):
        self.base_url = "https://api.core.ac.uk/v3/"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def search_publications(self, query, filters=None, sort=None, limit=10):
        endpoint = "search/works"
        params = {"q": query, "limit": limit}
        if filters:
            filter_expressions = []
            for key, value in filters.items():
                filter_expressions.append(f"{key}:{value}")
            params["filter"] = ",".join(filter_expressions)
        if sort:
            params["sort"] = sort

        r = requests.get(
            self.base_url + endpoint,
            headers=self.headers,
            params=params,
            timeout=15
        )
        r.raise_for_status()
        return r.json()


##############################################################################
# Hilfsfunktionen für einzelne Such-APIs
##############################################################################

def search_europe_pmc(query):
    """Einfache Abfrage über Europe PMC."""
    results = []
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "pageSize": 50, "resultType": "core"}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "resultList" in data and "result" in data["resultList"]:
            for item in data["resultList"]["result"]:
                title = item.get("title", "n/a")
                authors = item.get("authorString", "n/a")
                journ = item.get("journalTitle", "n/a")
                year = item.get("pubYear", "n/a")
                pmid = item.get("pmid", "n/a")
                pmcid = item.get("pmcid", "")
                doi = item.get("doi", "")
                abstract_text = item.get("abstractText", "")

                if pmcid:
                    # Europe PMC-URL
                    if not pmcid.startswith("PMC"):
                        pmcid = "PMC" + pmcid
                    url_article = f"https://europepmc.org/articles/{pmcid}"
                elif pmid:
                    url_article = f"https://europepmc.org/article/MED/{pmid}"
                elif doi:
                    url_article = f"https://doi.org/{doi}"
                else:
                    url_article = "n/a"

                results.append({
                    "Source": "Europe PMC",
                    "Title": title,
                    "Authors": authors,
                    "Journal": journ,
                    "Year": year,
                    "PMID": pmid,
                    "DOI": doi,
                    "URL": url_article,
                    "Abstract": abstract_text
                })
    except Exception as e:
        st.warning(f"Europe PMC Error: {e}")
    return results


def search_pubmed(query):
    """Einfache PubMed-Suche über E-Utilities (esearch + Zusammenfassung)."""
    results = []
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": 50}
    try:
        r = requests.get(esearch_url, params=params, timeout=10)
        r.raise_for_status()
        js = r.json()
        idlist = js.get("esearchresult", {}).get("idlist", [])
        if not idlist:
            return results

        # eSummary
        esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        sum_params = {"db": "pubmed", "id": ",".join(idlist), "retmode": "json"}
        sum_resp = requests.get(esummary_url, params=sum_params, timeout=10)
        sum_resp.raise_for_status()
        sum_data = sum_resp.json()

        for pmid in idlist:
            summ = sum_data.get("result", {}).get(pmid, {})
            if not summ:
                continue

            title = summ.get("title", "n/a")
            authors_list = summ.get("authors", [])
            authors = ", ".join(a.get("name", "") for a in authors_list)
            journ = summ.get("fulljournalname", "n/a")
            pub_date = summ.get("pubdate", "n/a")[:4]
            pmid_val = pmid
            doi = summ.get("elocationid", "n/a")
            url_article = f"https://pubmed.ncbi.nlm.nih.gov/{pmid_val}/"

            # Einfacher eFetch fürs Abstract (Beispiel)
            abstract_text = fetch_pubmed_abstract(pmid_val)

            results.append({
                "Source": "PubMed",
                "Title": title,
                "Authors": authors,
                "Journal": journ,
                "Year": pub_date,
                "PMID": pmid_val,
                "DOI": doi,
                "URL": url_article,
                "Abstract": abstract_text
            })
    except Exception as e:
        st.warning(f"PubMed Error: {e}")
    return results


def fetch_pubmed_abstract(pmid):
    """Holt das Abstract via eFetch (vereinfacht)."""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        abs_text = ""
        for elem in root.findall(".//AbstractText"):
            if elem.text:
                abs_text += (elem.text + "\n")
        if not abs_text.strip():
            abs_text = "(Kein Abstract)"
        return abs_text.strip()
    except:
        return "(Abstract nicht verfügbar)"


def search_ensembl(species, gene):
    """Beispiel für Ensembl REST-API."""
    results = []
    base_url = "https://rest.ensembl.org"
    endpoint = f"/lookup/symbol/{species}/{gene}"
    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.get(base_url + endpoint, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        desc_str = f"chr: {data.get('seq_region_name', 'n/a')}, strand: {data.get('strand', 'n/a')}"
        ensembl_url = f"https://www.ensembl.org/{species}/Gene/Summary?g={data.get('id','')}"

        results.append({
            "Source": "Ensembl REST",
            "Title": data.get("display_name", gene),
            "Authors": desc_str,
            "Journal": data.get("species", "n/a"),
            "Year": "n/a",
            "PMID": "n/a",
            "DOI": "n/a",
            "URL": ensembl_url,
            "Abstract": "(Kein Paper-Abstract, da Gen-Daten)"
        })
    except Exception as e:
        st.warning(f"Ensembl Error: {e}")
    return results


def search_uniprot(protein):
    """Beispiel für UniProt-Suche per REST-API."""
    results = []
    try:
        # 1) Kurze Suche
        url_search = f"https://rest.uniprot.org/uniprotkb/search?query={protein}&format=json&size=1"
        resp1 = requests.get(url_search, timeout=10)
        resp1.raise_for_status()
        data_search = resp1.json()
        found = data_search.get("results", [])
        if not found:
            return results

        accession = found[0].get("primaryAccession", "")
        if not accession:
            return results

        # 2) Detail-Request
        url_detail = f"https://rest.uniprot.org/uniprotkb/{accession}.json"
        resp2 = requests.get(url_detail, timeout=10)
        resp2.raise_for_status()
        data_detail = resp2.json()

        protein_name = data_detail.get("proteinDescription", {}).get("recommendedName", {}).get("fullName", {}).get("value", "n/a")
        organism = data_detail.get("organism", {}).get("scientificName", "n/a")
        seq_len = data_detail.get("sequence", {}).get("length", "n/a")
        url_article = f"https://www.uniprot.org/uniprotkb/{accession}"
        authors_description = f"Organismus: {organism}; Länge: {seq_len}"

        results.append({
            "Source": "UniProt",
            "Title": protein_name,
            "Authors": authors_description,
            "Journal": organism,
            "Year": "n/a",
            "PMID": "n/a",
            "DOI": "n/a",
            "URL": url_article,
            "Abstract": "(Kein Abstract)"
        })
    except Exception as e:
        st.warning(f"UniProt Error: {e}")
    return results


def search_openalex(query):
    """Einfache OpenAlex-Suche."""
    results = []
    url = f"https://api.openalex.org/works?filter=title.search:{query}&sort=cited_by_count:desc&per-page=10"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        for work in data.get("results", []):
            title = work.get("title", "n/a")
            auths = work.get("authorships", [])
            authors = ", ".join(a["author"]["display_name"] for a in auths[:3])
            if len(auths) > 3:
                authors += " et al."
            year = work.get("publication_year", "n/a")
            doi = work.get("doi", "n/a")
            host_venue = work.get("host_venue", {})
            journ = host_venue.get("display_name", "n/a")
            abstract_text = work.get("abstract", "")
            url_article = "n/a"
            if doi != "n/a":
                url_article = "https://doi.org/" + doi.replace("https://doi.org/", "")

            results.append({
                "Source": "OpenAlex",
                "Title": title,
                "Authors": authors,
                "Journal": journ,
                "Year": str(year),
                "PMID": "n/a",
                "DOI": doi,
                "URL": url_article,
                "Abstract": abstract_text
            })
    except Exception as e:
        st.warning(f"OpenAlex Error: {e}")
    return results


def search_semantic_scholar(query):
    """Einfache Semantic Scholar-Suche."""
    results = []
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        headers = {"Accept": "application/json"}
        params = {
            "query": query,
            "limit": 10,
            "fields": "title,authors,year,abstract,doi,paperId"
        }
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        for paper in data.get("data", []):
            title = paper.get("title", "n/a")
            authors = ", ".join(a.get("name", "") for a in paper.get("authors", []))
            year = paper.get("year", "n/a")
            doi = paper.get("doi", "n/a")
            paper_id = paper.get("paperId", "")
            abstract_text = paper.get("abstract", "")
            url_article = f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else "n/a"

            results.append({
                "Source": "Semantic Scholar",
                "Title": title,
                "Authors": authors,
                "Journal": "n/a",
                "Year": str(year),
                "PMID": "n/a",
                "DOI": doi,
                "URL": url_article,
                "Abstract": abstract_text
            })
    except Exception as e:
        st.warning(f"Semantic Scholar Error: {e}")
    return results


def search_core_aggregate(query):
    """Einfache CORE-Suche."""
    results = []
    API_KEY = "YOUR_CORE_API_KEY"  # Anpassen
    core = CoreAPI(API_KEY)
    filters = {"yearPublished": ">=2020,<=2025", "language.name": "English"}
    sort = "citationCount:desc"
    limit = 10
    try:
        data = core.search_publications(query=query, filters=filters, sort=sort, limit=limit)
        for pub in data.get("results", []):
            title = pub.get("title", "n/a")
            doi = pub.get("doi", "n/a")
            year = pub.get("yearPublished", "n/a")
            authors = ", ".join(pub.get("authors", []))
            downloadUrl = pub.get("downloadUrl", "n/a")
            abstract = pub.get("abstract", "")
            publisher = pub.get("publisher", "n/a")

            results.append({
                "Source": "CORE Aggregate",
                "Title": title,
                "Authors": authors,
                "Journal": publisher,
                "Year": str(year),
                "PMID": "n/a",
                "DOI": doi,
                "URL": downloadUrl,
                "Abstract": abstract
            })
    except Exception as e:
        st.warning(f"CORE Aggregate Error: {e}")
    return results

def search_dbSNP(rs_id):
    """Beispielhafte Einbindung der dbSNP-Klasse."""
    dbsnp_api = DBSnpAPI(email="some@email.com", api_key="SOME_API_KEY")
    info = dbsnp_api.get_snp_info(rs_id)
    return info


##############################################################################
# Streamlit-App
##############################################################################

def run_streamlit_app():
    st.title("Streamlit App: Verschiedene API-Suchen")

    st.subheader("1. Wähle eine oder mehrere APIs aus:")
    api_list = [
        "Europe PMC",
        "PubMed",
        "Ensembl REST",
        "UniProt",
        "OpenAlex",
        "Semantic Scholar",
        "CORE Aggregate",
        "dbSNP"
        # Google Scholar ist tricky wegen „scholarly“-Lib und Captcha
        # "Google Scholar"
    ]
    selected_apis = st.multiselect("APIs", api_list, default=["Europe PMC"])

    st.subheader("2. Suchbegriff oder RS-ID eingeben:")
    query = st.text_input("Such-Query (z.B. 'Cancer biomarker' oder 'APOE')", "")
    rs_id = st.text_input("Oder eine dbSNP-RS-ID (z.B. rs429358)", "")

    if st.button("Suche starten"):
        all_results = []

        # Beispiel: Falls wir dbSNP ausgewählt haben und der/die Nutzer:in eine RS-ID eingibt
        if "dbSNP" in selected_apis and rs_id:
            dbsnp_result = search_dbSNP(rs_id)
            if dbsnp_result:
                st.write("dbSNP-Ergebnis:", dbsnp_result)
            else:
                st.warning("Keine Daten zu dieser RS-ID gefunden oder Fehler aufgetreten.")

        # Falls wir zusätzlich 'normale' Query-APIs nutzen wollen:
        if query.strip():
            if "Europe PMC" in selected_apis:
                results_epmc = search_europe_pmc(query)
                all_results.extend(results_epmc)

            if "PubMed" in selected_apis:
                results_pubmed = search_pubmed(query)
                all_results.extend(results_pubmed)

            if "Ensembl REST" in selected_apis:
                # Ensembl braucht Spezies & Gen-Symbol; wir nehmen hier ein Platzhalter-Beispiel
                # Du könntest das in der UI mit st.text_input(spezies) / st.text_input(gene) realisieren.
                ensembl_species = "homo_sapiens"
                ensembl_gene = query  # Annahme: user tippt Gen an
                ensembl_results = search_ensembl(ensembl_species, ensembl_gene)
                all_results.extend(ensembl_results)

            if "UniProt" in selected_apis:
                uniprot_results = search_uniprot(query)
                all_results.extend(uniprot_results)

            if "OpenAlex" in selected_apis:
                oa_results = search_openalex(query)
                all_results.extend(oa_results)

            if "Semantic Scholar" in selected_apis:
                semsch_results = search_semantic_scholar(query)
                all_results.extend(semsch_results)

            if "CORE Aggregate" in selected_apis:
                core_results = search_core_aggregate(query)
                all_results.extend(core_results)

            if all_results:
                st.success(f"Insgesamt {len(all_results)} Treffer erhalten.")
                # Ausgabe als DataFrame (Tabellenansicht)
                # Wir reduzieren die Dicts, damit es übersichtlich bleibt
                display_data = [
                    {
                        "Source": r["Source"],
                        "Title": r["Title"][:80] + ("..." if len(r["Title"]) > 80 else ""),
                        "Authors": r["Authors"][:50] + ("..." if len(r["Authors"]) > 50 else ""),
                        "Year": r["Year"],
                        "PMID": r["PMID"],
                        "DOI": r["DOI"],
                        "URL": r["URL"] if r["URL"] != "n/a" else ""
                    }
                    for r in all_results
                ]
                st.dataframe(display_data)
            else:
                st.warning("Keine Treffer gefunden oder Fehler aufgetreten.")
        else:
            st.warning("Bitte ein Such-Query eingeben oder eine RS-ID. (Oder beides)")

    st.write("---")
    st.info("Dies ist ein stark vereinfachtes Beispiel, wie man die API-Logik aus dem Tkinter-Skript "
            "in eine Streamlit-App integrieren kann. Die Filter-, PDF- und Excel-Exportfunktionen "
            "müsstest du bei Bedarf analog umsetzen (z. B. über Buttons und st.download_button).")


# Standard Streamlit-Einstieg:
if __name__ == "__main__":
    run_streamlit_app()
