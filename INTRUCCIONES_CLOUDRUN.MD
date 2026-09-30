# Autenticar a GCP
gcloud --version
gcloud auth login
gcloud projects list

# Seleccionar Proyecto
gcloud config set project big-data-movistar
gcloud config get-value project

# Verificar Proyecto
$projectId = "big-data-movistar"
$region = "us-east4"

gcloud config set project $projectId
gcloud config set run/region $region

gcloud billing projects describe $projectId
gcloud config get-value run/region

# Habilitar Servicios
gcloud services enable `
  run.googleapis.com `
  artifactregistry.googleapis.com `
  secretmanager.googleapis.com `
  cloudbuild.googleapis.com

  gcloud config list

  # Crear Secret en GCP
  Google Cloud Console
    → Security
    → Secret Manager
    → Create secret

    Names: tacticas-prod, tacticas-dev y bj-prod

# Agregar fila a .gitignore
deploy/cloudrun/service.rendered.yaml


## Cuenta de Servicio de Cloud Run
gcloud iam service-accounts create gcpbrowser-cloudrun `
  --display-name="GCPBrowser Cloud Run"

# Damos acceso a la cuenta a los secrets
$runtime_sa = "gcpbrowser-cloudrun@$projectId.iam.gserviceaccount.com"

gcloud secrets add-iam-policy-binding tacticas-prod `
  --member="serviceAccount:$runtime_sa" `
  --role="roles/secretmanager.secretAccessor" `
  --project=$projectId

gcloud secrets add-iam-policy-binding tacticas-dev `
  --member="serviceAccount:$runtime_sa" `
  --role="roles/secretmanager.secretAccessor" `
  --project=$projectId

gcloud secrets add-iam-policy-binding bj-prod `
  --member="serviceAccount:$runtime_sa" `
  --role="roles/secretmanager.secretAccessor" `
  --project=$projectId

# Creamos los recursos iniciales manualmente una sola vez.
## Repo
gcloud artifacts repositories create gcp-browser `
  --repository-format=docker `
  --location=us-east4 `
  --description="Imagenes del GCP Browser"


# Permitir que Cloud Build publique imágenes en Artifact Registry
$projectNumber = gcloud projects describe big-data-movistar --format="value(projectNumber)"

gcloud projects add-iam-policy-binding big-data-movistar `
  --member="serviceAccount:$projectNumber@cloudbuild.gserviceaccount.com" `
  --role="roles/artifactregistry.writer"


# Deploy
.\deploy\cloudrun\deploy-cloud-run.ps1 `
  -ProjectId $project_id `
  -Region us-east4 `
  -RuntimeServiceAccount "gcpbrowser-cloudrun@$project_id.iam.gserviceaccount.com"

# Habilitar acceso público
gcloud run services add-iam-policy-binding gcs-data-browser `
  --region us-east4 `
  --member="allUsers" `
  --role="roles/run.invoker"

# Para confirmar la nueva versión
.\deploy\cloudrun\deploy-cloud-run.ps1 `
  -ProjectId $project_id `
  -Region us-east4 `
  -RuntimeServiceAccount "gcpbrowser-cloudrun@$project_id.iam.gserviceaccount.com"


# Para conocer la URL externa
gcloud run services describe gcs-data-browser `
  --region us-east4 `
  --format="value(status.url)"

  URL Ejemplo: URL: https://gcs-data-browser-z7enknj5za-uk.a.run.app

