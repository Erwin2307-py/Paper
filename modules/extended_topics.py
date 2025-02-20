import streamlit as st
import openai

def module_extended_topics():
    st.header("Modul 6: Erweiterte Themen & Upload")

    snp_input = st.text_input("Gib einen SNP (z.B. rs429358) oder ein Thema ein", "")
    if st.button("Themenvorschläge (ChatGPT)"):
        if not snp_input:
            st.warning("Bitte erst ein SNP/Thema eingeben.")
            return
        # Beispielaufruf ChatGPT (Pseudo)
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": f"SNP/Thema: {snp_input}. Bitte Ideen vorschlagen."}],
                temperature=0.7
            )
            ans = response.choices[0].message.content.strip()
            st.write(ans)
        except Exception as e:
            st.error(f"Fehler ChatGPT: {e}")

    st.subheader("Upload einer Studie (PDF o. Text)")
    uploaded_file = st.file_uploader("Datei hochladen", type=["pdf","txt"])
    if uploaded_file is not None:
        st.write(f"Datei hochgeladen: {uploaded_file.name}")
        # Hier könntest du PDF auslesen etc.
        # ...
