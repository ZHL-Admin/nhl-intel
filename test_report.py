"""Test the full reporting pipeline."""
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

# Test with date that has data
date = "2026-05-29"

print(f"Generating report for {date}...")
print("=" * 80)

# Step 1: Query data
print("1. Querying data...")
report_data = get_daily_report_data(date)
print(f"   Found {len(report_data)} data points")

# Step 2: Generate summary
print("2. Generating summary...")
summary = generate_summary(report_data)
print(f"   Summary: {summary[:100]}...")

# Step 3: Render HTML
print("3. Rendering HTML...")
html = render_report(report_data, summary, date)
print(f"   Generated {len(html)} characters of HTML")

# Step 4: Write to file
output_path = Path("/Users/codytownsend/Desktop/nhl/NIR/output/report_2026-05-29.html")
output_path.parent.mkdir(exist_ok=True)
output_path.write_text(html)

print(f"\nReport saved to: {output_path}")
print("Open in browser to view!")
