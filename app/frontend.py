import streamlit as st
from app.main import generate_answer, retrieve_chunks, embed_query
from app.entity_resolver import resolve_form

st.set_page_config(page_title="Mise RAG Assistant", page_icon="♻️")
st.title("♻️ Mise.ax RAG Assistant")
st.caption("Ask questions")


if "history" not in st.session_state:
    st.session_state.history = []


show_chunks = st.sidebar.checkbox("Show retrieved chunks (debug mode)", value=False)
if st.sidebar.button("Clear history"):
    st.session_state.history = []
    st.rerun()


with st.form(key="ask_form"):
    question = st.text_input(
        "Ask a question:", placeholder="Vad kostar det att slänga skrotfordon?"
    )
    submitted = st.form_submit_button("Ask")


if submitted and question.strip():
    with st.spinner("Searching and generating answer..."):
        query_embedding = embed_query(question)
        chunks = retrieve_chunks(query_embedding)
        answer = generate_answer(question, chunks=chunks)
        form_match = resolve_form(question)

    st.session_state.history.append(
        {
            "question": question,
            "answer": answer,
            "chunks": chunks,
            "form_match": form_match,
        }
    )


for entry in reversed(st.session_state.history):
    st.markdown(f"**Q:** {entry['question']}")
    st.markdown(f"**A:** {entry['answer']}")

    if entry["form_match"]:
        st.info(f"Possible related form: {entry['form_match']['form_name']}")

    if show_chunks:
        with st.expander("Retrieved chunks"):
            if not entry["chunks"]:
                st.write("No chunks retrieved.")
            for text, filename, similarity in entry["chunks"]:
                st.markdown(f"**{filename}** (similarity: {similarity:.3f})")
                st.text(text[:500] + ("..." if len(text) > 500 else ""))

    st.divider()
