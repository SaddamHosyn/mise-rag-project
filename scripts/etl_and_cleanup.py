import os
import shutil
import zipfile
import json
from db_connector import get_connection
import time
import gc

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "..", "data", "raw")
EXTRACT_DIR = os.path.join(BASE_DIR, "..", "data", "extracted")


def extract_zip(zip_name, extract_subfolder):
    zip_path = os.path.join(RAW_DIR, zip_name)
    extract_path = os.path.join(EXTRACT_DIR, extract_subfolder)

    print(f"Extracting {zip_path} -> {extract_path}")
    os.makedirs(extract_path, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_path)

    return zip_path, extract_path


def insert_companyfacts(cursor, filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    cik = str(data.get("cik", "")).zfill(10)
    entity_name = data.get("entityName", "")

    cursor.execute(
        "INSERT INTO companies (cik, entity_name) VALUES (%s, %s) ON CONFLICT (cik) DO NOTHING",
        (cik, entity_name),
    )

    tag_map = {
        "Revenues": "Revenue",
        "SalesRevenueNet": "Revenue",
        "RevenueFromContractWithCustomerExcludingAssessedTax": "Revenue",
        "NetIncomeLoss": "NetIncome",
        "Assets": "Assets",
        "Liabilities": "Liabilities",
    }

    usgaap = data.get("facts", {}).get("us-gaap", {})
    for tag, clean_name in tag_map.items():
        if tag in usgaap:
            for unit, records in usgaap[tag]["units"].items():
                for r in records:
                    cursor.execute(
                        """INSERT INTO financials (cik, metric_name, fiscal_year, fiscal_period, unit, value, filed_date)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (
                            cik,
                            clean_name,
                            r.get("fy"),
                            r.get("fp"),
                            unit,
                            r.get("val"),
                            r.get("filed"),
                        ),
                    )


def verify_data_integrity(cursor, table="financials", expected_min_rows=100):
    cursor.execute(f"SELECT COUNT(*) FROM {table};")
    row_count = cursor.fetchone()[0]
    if row_count < expected_min_rows:
        raise ValueError(f"Integrity check failed: only {row_count} rows in {table}")
    print(f"Integrity check passed: {row_count} rows in {table}")


def cleanup_raw_files(zip_path, extract_path, retries=3, delay=2):
    if os.path.exists(zip_path):
        os.remove(zip_path)
        print(f"Deleted: {zip_path}")

    gc.collect()  # Force Python to release any lingering file handles

    for attempt in range(retries):
        try:
            if os.path.exists(extract_path):
                shutil.rmtree(extract_path)
                print(f"Deleted folder: {extract_path}")
            return
        except PermissionError as e:
            print(
                f"Attempt {attempt + 1}/{retries} failed: {e}. Retrying in {delay}s..."
            )
            time.sleep(delay)

    print(
        f"Warning: Could not delete {extract_path} after {retries} attempts. Please delete manually."
    )


def run():
    zip_path, extract_path = extract_zip("companyfacts.zip", "companyfacts")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        json_files = [f for f in os.listdir(extract_path) if f.endswith(".json")]
        for i, filename in enumerate(json_files):
            filepath = os.path.join(extract_path, filename)
            insert_companyfacts(cursor, filepath)
            if i % 500 == 0:
                print(f"Processed {i}/{len(json_files)}")

        conn.commit()
        verify_data_integrity(cursor)
        cleanup_raw_files(zip_path, extract_path)

    except Exception as e:
        print(f"Error: {e}. Rolling back.")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    run()
