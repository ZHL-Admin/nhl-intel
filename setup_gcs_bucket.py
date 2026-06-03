"""Create and configure GCS bucket for public static file hosting."""
import os
from google.cloud import storage

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/codytownsend/Desktop/nhl/NIR/secrets/nhl-intel-sa.json'

bucket_name = "nhl-intel-reports"
project_id = "nhl-intel-498216"

print(f"Setting up GCS bucket: {bucket_name}")
print("=" * 80)

client = storage.Client(project=project_id)

# Check if bucket exists
try:
    bucket = client.get_bucket(bucket_name)
    print(f"Bucket {bucket_name} already exists")
except Exception:
    print(f"Creating bucket {bucket_name}...")
    bucket = client.create_bucket(bucket_name, location="US")
    print(f"Bucket {bucket_name} created")

# Enable uniform bucket-level access
bucket.iam_configuration.uniform_bucket_level_access_enabled = True
bucket.patch()
print("Uniform bucket-level access enabled")

# Make bucket publicly readable
policy = bucket.get_iam_policy(requested_policy_version=3)
policy.bindings.append({
    "role": "roles/storage.objectViewer",
    "members": {"allUsers"}
})
bucket.set_iam_policy(policy)
print("Bucket configured for public read access")

print("\nBucket setup complete!")
print(f"Public URL pattern: https://storage.googleapis.com/{bucket_name}/report_YYYY-MM-DD.html")
