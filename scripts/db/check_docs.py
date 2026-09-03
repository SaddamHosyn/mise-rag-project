from app.config import get_connection

conn = get_connection()
cursor = conn.cursor()
cursor.execute(
    "SELECT chunk_text, filename FROM document_chunks dc JOIN documents d ON dc.document_id = d.id WHERE chunk_text LIKE '%3 stycken%' OR chunk_text LIKE '%kylmöbler%';"
)
rows = cursor.fetchall()
print(f"Found {len(rows)} rows")
for r in rows:
    print("---", r[1])
    print(r[0][:300])
cursor.close()
conn.close()
