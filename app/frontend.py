import streamlit as st
from main import generate_answer_with_metrics, retrieve_chunks, embed_query
from entity_resolver import resolve_form

st.set_page_config(page_title="Mise RAG Assistant", page_icon="♻️")
st.title("♻️ Mise.ax RAG Assistant")
st.caption("Ask questions about waste fees, sorting rules, and municipal policies.")


if "history" not in st.session_state:
    st.session_state.history = []


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
show_chunks = st.sidebar.checkbox("Show retrieved chunks (debug mode)", value=False)
show_metrics = st.sidebar.checkbox("Show latency & cost metrics", value=True)

if st.sidebar.button("Clear history"):
    st.session_state.history = []
    st.rerun()


# ---------------------------------------------------------------------------
# Cache: identical questions skip embedding + DB + API for 1 hour
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def cached_answer(question: str) -> dict:
    """
    Returns generate_answer_with_metrics result cached by question text.
    Cache TTL = 1 hour. This saves API cost and reduces latency for repeated queries.
    """
    return generate_answer_with_metrics(question)


# ---------------------------------------------------------------------------
# Input form
# ---------------------------------------------------------------------------
with st.form(key="ask_form"):
    question = st.text_input(
        "Ask a question:", placeholder="Vad kostar det att slänga skrotfordon?"
    )
    submitted = st.form_submit_button("Ask")


if submitted and question.strip():
    with st.spinner("Searching and generating answer..."):
        # Fetch cached or fresh answer with metrics
        result = cached_answer(question)
        answer = result["answer"]
        latency_ms = result["latency_ms"]
        cost_usd = result["cost_usd"]

        # Retrieve chunks and form match (not cached — lightweight DB calls)
        query_embedding = embed_query(question)
        chunks = retrieve_chunks(query_embedding)
        form_match = resolve_form(question)

    st.session_state.history.append(
        {
            "question": question,
            "answer": answer,
            "chunks": chunks,
            "form_match": form_match,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
        }
    )


# ---------------------------------------------------------------------------
# Render conversation history
# ---------------------------------------------------------------------------
for entry in reversed(st.session_state.history):
    st.markdown(f"**Q:** {entry['question']}")
    st.markdown(f"**A:** {entry['answer']}")

    if entry["form_match"]:
        st.info(f"Possible related form: {entry['form_match']['form_name']}")

    # Performance metrics row
    if show_metrics:
        col1, col2 = st.columns(2)
        col1.metric("⏱ Latency", f"{entry['latency_ms']:.0f} ms")
        col2.metric("💰 Cost / query", f"${entry['cost_usd']:.6f}")

    if show_chunks:
        with st.expander("Retrieved chunks"):
            if not entry["chunks"]:
                st.write("No chunks retrieved.")
            for text, filename, similarity in entry["chunks"]:
                st.markdown(f"**{filename}** (similarity: {similarity:.3f})")
                st.text(text[:500] + ("..." if len(text) > 500 else ""))

    st.divider()
