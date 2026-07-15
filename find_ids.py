from app.config import get_connection

conn = get_connection()
cursor = conn.cursor()

cursor.execute(
    "SELECT id, filename FROM documents WHERE filename LIKE '%avfallstaxa-2026%';"
)
rows = cursor.fetchall()

for r in rows:
    print(r)

cursor.close()
conn.close()
