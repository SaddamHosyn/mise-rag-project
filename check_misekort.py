from app.config import get_connection

conn = get_connection()
cursor = conn.cursor()
cursor.execute(
    "SELECT chunk_text FROM document_chunks WHERE chunk_text LIKE '%Misekort%' AND chunk_text LIKE '%Rubrik%';"
)
rows = cursor.fetchall()
print(f"Found {len(rows)} Misekort rows with Rubrik tag")
for r in rows:
    print("---")
    print(r[0][:250])
cursor.close()
conn.close()
