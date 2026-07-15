from scripts.ingest_mise import extract_tables_as_text

test_file = "mise-scraped-data/output/mise_pdfs/mise.ax__sites_default_files_2025-12_avfallstaxa-2026-godkand-av-stamman-17.12.2025.pdf.pdf"

rows = extract_tables_as_text(test_file)
for r in rows:
    if "Misekort" in r:
        print(r)
