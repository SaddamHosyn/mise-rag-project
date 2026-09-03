import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "sslmode": os.getenv("DB_SSLMODE", "prefer"),
}


def get_connection():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    if not all([DB_CONFIG["dbname"], DB_CONFIG["user"], DB_CONFIG["password"]]):
        raise ValueError(
            "Missing required database environment variables. Check your .env file."
        )
    return psycopg2.connect(**DB_CONFIG)
