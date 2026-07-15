import os
from dotenv import load_dotenv
from pathlib import Path
from google import genai
from google.genai import types
from config import get_connection
from entity_resolver import resolve_form
import time
from google.genai.errors import ServerError

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


EMBED_MODEL = "gemini-embedding-001"
GEN_MODEL = "gemini-3-flash-preview"
TOP_K = 12


def embed_query(text: str):
    result = client.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=768),
    )
    return result.embeddings[0].values


def retrieve_chunks(query_embedding, top_k=TOP_K):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT dc.chunk_text, d.filename, 1 - (dc.embedding <=> %s::vector) AS similarity
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            ORDER BY 
                (dc.embedding <=> %s::vector) 
                - CASE 
                    WHEN d.filename LIKE '%%2026%%' THEN 0.15
                    WHEN d.filename LIKE '%%2025%%' THEN 0.08
                    ELSE 0
                  END
            LIMIT %s;
            """,
            (query_embedding, query_embedding, top_k),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def build_prompt(question, chunks):
    context = "\n\n".join(
        f"[Source: {filename}]\n{text}" for text, filename, _ in chunks
    )
    return f"""You are a helpful assistant answering questions about mise.ax waste management services.
Use ONLY the context below to answer. If the answer isn't in the context, say you don't know.





IMPORTANT RULES:
- If sources show different years of pricing (e.g. 2022, 2023, 2024, 2025, 2026), ALWAYS use the most recent year's price and explicitly state which year it's from.
- Do NOT combine or calculate prices by mixing figures from different years.
- Do NOT perform your own arithmetic (like multiplying "sopmärken" or "säckar") unless the exact total price is explicitly stated in the same source.
- Each context chunk may include a "[Rubrik: ...]" tag showing which document section it came from.
- Important terminology clarification: "Ej verksamhetskund" and "icke Misekunder" in the tariff document refer to (1) businesses without a registered Mise account, OR (2) any visitor/household who does not live in one of Mise's member municipalities (Hammarland, Jomala, Kökar, Lumparland, Mariehamn, Sottunga) — regardless of whether they identify as a private person or a business. If the question mentions living outside a Mise municipality, or being from another region, use the "Ej verksamhetskund per besök" fee (20,00 €), NOT the general household "Avgift för icke uppvisande av Misekort" (6,00 €), since that lower fee only applies to residents within Mise's area who simply forgot their card.
- For private household questions, ONLY use fees tagged under sections like "Grundavgifter", "Mottagningsavgifter... för hushåll", or similar wording that clearly says "hushåll". Ignore any fee tagged under a section mentioning "verksamhetskund" or "verksamheter" when answering about a private person, even if that chunk has a higher similarity score — UNLESS the question indicates the person lives outside Mise's member municipalities, in which case use the "Ej verksamhetskund" fee instead.
- For business questions, ONLY use fees tagged under sections mentioning "verksamheter" or "verksamhetskund".
- If you see the same fee type appearing under both a household-tagged section and a business-tagged section with different amounts, trust the [Rubrik] tag over anything else to decide which amount belongs in which category.
- When a question is about Misekort fees, ÅVC visit fees, or any fee that could differ between private households and businesses, first check whether the actual fee amount, process, or eligibility differs between "Privatpersoner/Hushåll" and "Företag/Verksamheter" in the context. If the amounts and rules are IDENTICAL for both groups (e.g. a flat fee like skrotfordon), present ONE unified answer without splitting into two sections. Only structure your answer with two separate sections ("Privatpersoner/Hushåll" and "Företag/Verksamheter") when the fee, process, or eligibility genuinely differs between the two groups.
- Do NOT guess a single fee when the context contains separate household and business rows. Use the [Rubrik: ...] tags to correctly assign each fee to the right category.
- Do NOT state specific numeric limits (e.g. "up to 3 items free") unless that exact number appears verbatim in the source text describing that specific item. If you are not certain a number is stated, do not invent one.





Context:
{context}





Question: {question}





Answer clearly and cite the source filename in brackets after relevant sentences."""


def generate_answer(question, chunks=None, retries=3):
    if chunks is None:
        query_embedding = embed_query(question)
        chunks = retrieve_chunks(query_embedding)

    if not chunks:
        return "Jag kunde inte hitta relevant information i kunskapsbasen."

    prompt = build_prompt(question, chunks)

    for attempt in range(retries):
        try:
            response = client.models.generate_content(model=GEN_MODEL, contents=prompt)
            return response.text
        except ServerError as e:
            if attempt < retries - 1:
                wait = 5 * (attempt + 1)
                print(
                    f"Server busy, retrying in {wait}s... (attempt {attempt + 1}/{retries})"
                )
                time.sleep(wait)
                continue
            return (
                "Systemet är tillfälligt överbelastat. Försök igen om en liten stund."
            )
        except Exception as e:
            print(f"Unexpected error: {e}")
            return "Ett oväntat fel uppstod. Försök igen om en liten stund."


def ask(question: str):
    form_match = resolve_form(question)
    answer = generate_answer(question)

    print(f"\nQ: {question}")
    if form_match:
        print(f"(Possible related form: {form_match['form_name']})")
    print(f"A: {answer}\n")
    return answer


if __name__ == "__main__":
    test_questions = [
        "Vad kostar det att slänga skrotfordon?",
        "Hur sorterar jag mitt avfall?",
        "Vilka öppettider har återvinningscentralen?",
    ]
    for q in test_questions:
        ask(q)
