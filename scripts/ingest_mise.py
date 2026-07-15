import os
import csv
import time
from dotenv import load_dotenv
import psycopg2
from google import genai
from google.genai import types
import pypdf
import docx
from pathlib import Path
import pdfplumber
import re


# 1. Setup & Connections
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

conn = psycopg2.connect(
    host=os.environ.get("DB_HOST", "localhost"),
    port=os.environ.get("DB_PORT", "5432"),
    dbname=os.environ.get("DB_NAME", "sec_rag_db"),
    user=os.environ.get("DB_USER", "raguser"),
    password=os.environ.get("DB_PASSWORD", ""),
)
cursor = conn.cursor()

# Directories
BASE_DIR = Path(__file__).resolve().parent.parent / "mise-scraped-data"
OUT_PAGES = BASE_DIR / "output/mise_pages"
OUT_PDFS = BASE_DIR / "output/mise_pdfs"
OUT_DOCS = BASE_DIR / "output/mise_docs"
FORMS_CSV = BASE_DIR / "output/forms_directory_draft.csv"


def clean_database():
    print("Clearing existing data for a fresh run...")
    cursor.execute(
        "TRUNCATE TABLE forms_directory, document_chunks, documents RESTART IDENTITY CASCADE;"
    )
    conn.commit()


def ingest_forms_directory():
    cursor.execute("SELECT COUNT(*) FROM forms_directory;")
    count = cursor.fetchone()[0]
    if count > 0:
        print(f"forms_directory already has {count} rows. Skipping re-ingest.")
        return

    print(f"Ingesting {FORMS_CSV}...")
    if not os.path.exists(FORMS_CSV):
        print("CSV not found, skipping.")
        return

    with open(FORMS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cursor.execute(
                """
                INSERT INTO forms_directory (form_name, category, file_type, source_url, description, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
            """,
                (
                    row.get("form_name"),
                    row.get("category"),
                    row.get("file_type"),
                    row.get("source_url"),
                    row.get("description"),
                    row.get("notes"),
                ),
            )
    conn.commit()
    print("Forms directory loaded.")


def extract_text(filepath):
    ext = str(filepath).lower().split(".")[-1]
    text = ""
    try:
        if ext == "txt":
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
        elif ext == "pdf":
            with open(filepath, "rb") as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
        elif ext in ["doc", "docx"]:
            doc = docx.Document(filepath)
            for para in doc.paragraphs:
                text += para.text + "\n"
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    return text.strip()


def chunk_text(text, chunk_size=1000, overlap=200):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def extract_tables_as_text(pdf_path):
    table_chunks = []
    current_section = ""
    heading_pattern = re.compile(r"^\d+(\.\d+)*\s+[A-ZÅÄÖ]")

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            for line in page_text.split("\n"):
                line = line.strip()
                if heading_pattern.match(line) and len(line) < 100:
                    current_section = line

            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                headers = [h.strip() if h else "" for h in table[0]]
                for row in table[1:]:
                    if not any(row):
                        continue
                    parts = []
                    for h, v in zip(headers, row):
                        if v is None or str(v).strip() == "":
                            continue
                        v = str(v).strip()
                        if h:
                            parts.append(f"{h}: {v}")
                        else:
                            parts.append(v)
                    if parts:
                        section_prefix = f"[Rubrik: {current_section}] " if current_section else ""
                        table_chunks.append(f"{section_prefix}[Page {page_num}] " + " | ".join(parts))
    return table_chunks

def is_already_processed(filename):
    cursor.execute("SELECT id FROM documents WHERE filename = %s", (filename,))
    return cursor.fetchone() is not None


def embed_with_retry(chunk, max_retries=5):
    for attempt in range(max_retries):
        try:
            result = client.models.embed_content(
                model="gemini-embedding-001",
                contents=chunk,
                config=types.EmbedContentConfig(output_dimensionality=768),
            )
            return result.embeddings[0].values
        except Exception as e:
            error_str = str(e)
            if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                wait_time = 60
                if "retryDelay" in error_str:
                    try:
                        wait_time = (
                            float(error_str.split("retryDelay': '")[1].split("s")[0])
                            + 2
                        )
                    except:
                        pass
                print(
                    f"    -> Quota hit. Waiting {wait_time:.0f}s before retry {attempt+1}/{max_retries}..."
                )
                time.sleep(wait_time)
            else:
                print(f"    -> Non-quota error: {e}")
                return None
    print("    -> Max retries exceeded for this chunk. Skipping.")
    return None


def ingest_documents():
    folders = [OUT_PAGES, OUT_PDFS, OUT_DOCS]

    for folder in folders:
        if not os.path.exists(folder):
            continue

        for filename in os.listdir(folder):
            filepath = os.path.join(folder, filename)
            if not os.path.isfile(filepath):
                continue

            # Fix double-extension filenames (e.g. "name.pdf.pdf" -> "name.pdf")
            clean_filename = filename.replace(".pdf.pdf", ".pdf")

            if is_already_processed(clean_filename):
                print(f"Skipping (already in DB): {clean_filename}")
                continue

            print(f"Processing: {clean_filename}")

            text = extract_text(filepath)
            if len(text) < 50:
                print(f"  -> Skipping (too short or unreadable)")
                continue

            chunks = chunk_text(text)

            if str(filepath).lower().endswith(".pdf"):
                table_chunks = extract_tables_as_text(filepath)
                if table_chunks:
                    print(
                        f"  -> Found {len(table_chunks)} table rows in {clean_filename}"
                    )
                    chunks.extend(table_chunks)

            chunk_embeddings = []
            failed = False

            for i, chunk in enumerate(chunks):
                embedding = embed_with_retry(chunk)
                if embedding:
                    chunk_embeddings.append((i, chunk, embedding))
                else:
                    print(
                        f"  -> Chunk {i} failed permanently. Marking file incomplete."
                    )
                    failed = True
                    break
                time.sleep(1)

            if failed or not chunk_embeddings:
                print(
                    f"  -> Skipping save for {clean_filename} (incomplete embeddings)"
                )
                continue

            cursor.execute(
                """
                INSERT INTO documents (filename, source_url, file_type)
                VALUES (%s, %s, %s) RETURNING id;
            """,
                (clean_filename, "", clean_filename.split(".")[-1].upper()),
            )
            doc_id = cursor.fetchone()[0]

            for i, chunk, embedding in chunk_embeddings:
                cursor.execute(
                    """
                    INSERT INTO document_chunks (document_id, chunk_text, chunk_index, embedding)
                    VALUES (%s, %s, %s, %s)
                """,
                    (doc_id, chunk, i, embedding),
                )

            conn.commit()
            time.sleep(1)


if __name__ == "__main__":
    # clean_database()  # Commented out to preserve progress across runs
    ingest_forms_directory()
    ingest_documents()

    cursor.close()
    conn.close()
    print("Ingestion complete!")
