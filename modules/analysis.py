import streamlit as st

def module_analysis():
    st.header("Modul 5: Analyse & Bewertung")

    # Beispiel: Wir zeigen hier, wie man eine Bewertung speichert
    if "selected_papers" not in st.session_state or not st.session_state["selected_papers"]:
        st.info("Keine Paper ausgewählt.")
        return

    for paper_title in st.session_state["selected_papers"]:
        st.subheader(paper_title)
        rating_key = f"rating_{paper_title}"
        old_rating = st.session_state.get(rating_key, 0)
        new_rating = st.slider(f"Bewertung für {paper_title}", 0, 5, old_rating)
        st.session_state[rating_key] = new_rating

    if st.button("Gesamtanalyse"):
        ratings = []
        for paper_title in st.session_state["selected_papers"]:
            rkey = f"rating_{paper_title}"
            val = st.session_state.get(rkey, 0)
            ratings.append(val)
        if ratings:
            avg_rating = sum(ratings) / len(ratings)
            st.success(f"Durchschnittliche Bewertung: {avg_rating:.2f}")
        else:
            st.warning("Keine Bewertungen vorhanden.")
