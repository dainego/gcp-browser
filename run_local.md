$env:GCS_BUCKET_FILTER="tacticas-moviles-prod"
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\Users\diotero\OneDrive\A13 - GITHUB\gcp-browser\credentials\teco-prod-datalake-8f6a1.json"
pip install -r requirements.txt
uvicorn app.main:app --reload