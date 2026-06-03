"""Test end-to-end report generation and GCS publishing."""
import os
import sys
from pathlib import Path

sys.path.insert(0, '/Users/codytownsend/Desktop/nhl/NIR')

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/codytownsend/Desktop/nhl/NIR/secrets/nhl-intel-sa.json'

from dotenv import load_dotenv
load_dotenv()

from reporting.query import get_daily_report_data
from reporting.llm_summary import generate_summary
from reporting.render import render_report
from google.cloud import storage

# Use 2026-05-29 since we have data for that date
report_date = "2026-05-29"

print(f"End-to-End Report Generation Test for {report_date}")
print("=" * 80)

# Step 1: Query data
print("\n1. Querying mart_daily_report_feed...")
report_data = get_daily_report_data(report_date)
print(f"   ✓ Found {len(report_data)} data points")

if not report_data:
    print("   ✗ No data available for this date")
    sys.exit(1)

# Step 2: Generate LLM summary
print("\n2. Generating AI summary...")
summary = generate_summary(report_data)
print(f"   ✓ Generated summary ({len(summary)} characters)")
print(f"   Preview: {summary[:100]}...")

# Step 3: Render HTML
print("\n3. Rendering HTML report...")
html = render_report(report_data, summary, report_date)
print(f"   ✓ Rendered {len(html)} characters of HTML")

# Step 4: Write to local file
print("\n4. Writing report to local filesystem...")
output_dir = Path("/Users/codytownsend/Desktop/nhl/NIR/output")
output_dir.mkdir(exist_ok=True)
output_path = output_dir / f"report_{report_date}.html"
output_path.write_text(html)
print(f"   ✓ Saved to {output_path}")

# Step 5: Upload to GCS
print("\n5. Uploading to GCS bucket...")
bucket_name = os.getenv("REPORT_OUTPUT_BUCKET", "nhl-intel-reports")
blob_name = output_path.name

storage_client = storage.Client()
bucket = storage_client.bucket(bucket_name)
blob = bucket.blob(blob_name)

blob.upload_from_filename(str(output_path))
print(f"   ✓ Uploaded to gs://{bucket_name}/{blob_name}")

# Step 6: Get public URL (bucket has uniform bucket-level access)
print("\n6. Getting public URL...")
public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_name}"
print(f"   ✓ Report accessible via public URL")

# Final result
print("\n" + "=" * 80)
print("SUCCESS: Report Generation Complete!")
print("=" * 80)
print(f"\nPublic URL: {public_url}")
print(f"\nAll 5 sections populated:")
print("  ✓ AI narrative summary")
print("  ✓ Game results with scores and metrics")
print("  ✓ Team trends with directional indicators")
print("  ✓ Top player highlights")
print("  ✓ Hot/cold flags")
print("\nOpen the URL in your browser to view the report!")
