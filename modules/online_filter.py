import streamlit as st

def module_online_filter():
    st.header("Modul 2: Online-Filter")

    if "filter_options" not in st.session_state:
        st.session_state["filter_options"] = {
            "use_local": True,
            "use_chatgpt": False,
            "use_gene_excel": False,
            "extra_term": ""
        }

    flt = st.session_state["filter_options"]
    flt["use_local"] = st.checkbox("Lokaler Filter (genotype, phenotype, ...)", value=flt["use_local"])
    flt["use_chatgpt"] = st.checkbox("ChatGPT-Filter", value=flt["use_chatgpt"])
    flt["use_gene_excel"] = st.checkbox("Gene (Excel)", value=flt["use_gene_excel"])
    extra_inp = st.text_input("Extra-Filterbegriff", value=flt["extra_term"])
    flt["extra_term"] = extra_inp

    st.session_state["filter_options"] = flt
    st.write("Aktuelle Filter-Einstellungen:", flt)
