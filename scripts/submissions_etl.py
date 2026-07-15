import os
import shutil
import zipfile
import json
import time
import gc
from db_connector import get_connection

BASE_DIR = os.path.dirname(__file__)
RAW_DIR = os.path.join(BASE_DIR, "..", "data", "raw")
EXTRACT_DIR = os.path.join(BASE_DIR, "..", "data", "extracted")

def extract_zip(zip_name, extract_subfolder):
    zip_path = os.path.join(RAW_DIR, zip_name)
    extract_path = os.path.join(EXTRACT_DIR, extract_subfolder)
    
    print(f"Extracting {zip_path} -> {extract_path}")
    os.makedirs(extract_path, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(extract_path)
    
    return zip_path, extract_path

def update_company_metadata(cursor, filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    cik = str(data.get("cik", "")).zfill(10)
    tickers = data.get("tickers", [])
    ticker = tickers[0] if tickers else None  # Take primary ticker only
    sic_code = data.get("sic", "")
    sic_description = data.get("sicDescription", "")
    
    cursor.execute(
        """UPDATE companies 
           SET ticker = %s, sic_code = %s, sic_description = %s 
           WHERE cik = %s""",
        (ticker, sic_code, sic_description, cik)
    )
    
    # If the CIK doesn't exist yet (wasn't in companyfacts.zip), insert it
    if cursor.rowcount == 0:
        entity_name = data.get("name", "")
        cursor.execute(
            """INSERT INTO companies (cik, entity_name, ticker, sic_code, sic_description)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (cik) DO NOTHING""",
            (cik, entity_name, ticker, sic_code, sic_description)
        )

def verify_data_integrity(cursor, expected_min_rows=1000):
    cursor.execute("SELECT COUNT(*) FROM companies WHERE ticker IS NOT NULL;")
    row_count = cursor.fetchone()[0]
    if row_count < expected_min_rows:
        raise ValueError(f"Integrity check failed: only {row_count} companies have tickers")
    print(f"Integrity check passed: {row_count} companies now have tickers")

def cleanup_raw_files(zip_path, extract_path, retries=3, delay=2):
    if os.path.exists(zip_path):
        os.remove(zip_path)
        print(f"Deleted: {zip_path}")
    
    gc.collect()
    
    for attempt in range(retries):
        try:
            if os.path.exists(extract_path):
                shutil.rmtree(extract_path)
                print(f"Deleted folder: {extract_path}")
            return
        except PermissionError as e:
            print(f"Attempt {attempt + 1}/{retries} failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)
    
    print(f"Warning: Could not delete {extract_path}. Please delete manually.")

def run():
    zip_path, extract_path = extract_zip("submissions.zip", "submissions")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        json_files = [f for f in os.listdir(extract_path) if f.endswith(".json") and not f.startswith("CIK") is False]
        # Filter to only main CIK files (skip any submission history continuation files if present)
        json_files = [f for f in os.listdir(extract_path) if f.startswith("CIK") and f.endswith(".json")]
        
        total = len(json_files)
        for i, filename in enumerate(json_files):
            filepath = os.path.join(extract_path, filename)
            try:
                update_company_metadata(cursor, filepath)
            except Exception as row_err:
                print(f"Skipping {filename}: {row_err}")
                continue
            
            if i % 1000 == 0:
                print(f"Processed {i}/{total}")
                conn.commit()  # Commit in batches to avoid one giant transaction
        
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
