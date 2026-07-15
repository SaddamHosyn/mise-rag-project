import os
import psycopg2
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import urlparse, parse_qs

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("Missing DATABASE_URL environment variable. Check your .env file.")

_parsed = urlparse(DATABASE_URL)
_query = parse_qs(_parsed.query)

DB_CONFIG = {
    "host": _parsed.hostname,
    "port": _parsed.port or 5432,
    "dbname": _parsed.path.lstrip("/"),
    "user": _parsed.username,
    "password": _parsed.password,
    "sslmode": _query.get("sslmode", ["require"])[0],
}


def get_connection():
    return psycopg2.connect(DATABASE_URL)
