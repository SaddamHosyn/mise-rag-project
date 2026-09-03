from app.config import get_connection

conn = get_connection()
cursor = conn.cursor()

cursor.execute(
    "SELECT chunk_text FROM document_chunks WHERE chunk_text LIKE '%Rubrik%' LIMIT 5;"
)
rows = cursor.fetchall()

print(f"Found {len(rows)} rows with 'Rubrik' tag")
for r in rows:
    print("---")
    print(r[0][:200])

cursor.close()
conn.close()
