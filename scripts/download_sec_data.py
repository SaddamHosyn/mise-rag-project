import requests
import os

HEADERS = {"User-Agent": "MiseAlandProject contact@example.com"}
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

FILES = {
    "companyfacts.zip": "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip",
    "submissions.zip": "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
}

def download_file(filename, url):
    os.makedirs(RAW_DIR, exist_ok=True)
    filepath = os.path.join(RAW_DIR, filename)
    
    print(f"Downloading {filename}...")
    response = requests.get(url, headers=HEADERS, stream=True)
    
    if response.status_code == 200:
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Saved to {filepath}")
    else:
        print(f"Failed: {response.status_code}")

if __name__ == "__main__":
    for filename, url in FILES.items():
        download_file(filename, url)
