"""Test the LLM summary module."""
import os
import sys

sys.path.insert(0, '/Users/codytownsend/Desktop/nhl/NIR')

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/codytownsend/Desktop/nhl/NIR/secrets/nhl-intel-sa.json'

from dotenv import load_dotenv
load_dotenv()

from reporting.query import get_daily_report_data
from reporting.llm_summary import generate_summary

# Test with date that has data
date = "2026-05-29"
report_data = get_daily_report_data(date)

print(f"Generating summary for {date} with {len(report_data)} data points...")
print("=" * 80)

summary = generate_summary(report_data)
print("\nGenerated Summary:")
print(summary)
