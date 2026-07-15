import psycopg2
from app.config import DB_CONFIG


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def resolve_form(user_input: str):
    """
    Takes a raw string like 'skrotfordon' and returns the closest matching form.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT form_name, category, source_url FROM forms_directory WHERE form_name ILIKE %s LIMIT 1;",
            (f"%{user_input}%",),
        )
        result = cursor.fetchone()
        if result:
            return {
                "form_name": result[0],
                "category": result[1],
                "source_url": result[2],
                "match_type": "exact_contains",
            }

        cursor.execute(
            """SELECT form_name, category, source_url, similarity(form_name, %s) AS sim
               FROM forms_directory
               WHERE form_name %% %s
               ORDER BY sim DESC
               LIMIT 1;""",
            (user_input, user_input),
        )
        result = cursor.fetchone()
        if result:
            return {
                "form_name": result[0],
                "category": result[1],
                "source_url": result[2],
                "match_type": "fuzzy_name",
                "similarity": result[3],
            }

        return None
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    test_queries = ["skrotfordon", "avfallstaxa", "nedskrapning"]
    for q in test_queries:
        result = resolve_form(q)
        print(f"Query: '{q}' -> {result}")
