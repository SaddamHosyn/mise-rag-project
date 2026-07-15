#!/bin/bash
cd "$(dirname "$0")"

echo "Step 1: Downloading SEC bulk data..."
python scripts/download_sec_data.py

echo "Step 2: Running ETL and cleanup..."
python scripts/etl_and_cleanup.py

echo "Pipeline complete!"
