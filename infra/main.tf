terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "container_image" {
  description = "Fully qualified image, e.g. gcr.io/PROJECT/paybridge-reconciler:latest"
  type        = string
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# --- Least-privilege service account for the agent ---
resource "google_service_account" "agent" {
  account_id   = "paybridge-agent"
  display_name = "PayBridge reconciliation agent"
}

resource "google_project_iam_member" "agent_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_project_iam_member" "agent_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent.email}"
}

# --- Firestore (native mode) ---
resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
}

# --- Cloud Run service running the agent ---
resource "google_cloud_run_v2_service" "reconciler" {
  name     = "paybridge-reconciler"
  location = var.region

  template {
    service_account = google_service_account.agent.email
    containers {
      image = var.container_image
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
    }
  }
}

# Allow the scheduler's service account to invoke Cloud Run
resource "google_service_account" "scheduler" {
  account_id   = "paybridge-scheduler"
  display_name = "PayBridge Cloud Scheduler invoker"
}

resource "google_cloud_run_v2_service_iam_member" "scheduler_invoker" {
  name     = google_cloud_run_v2_service.reconciler.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

# --- Cloud Scheduler: trigger every 15 minutes ---
resource "google_cloud_scheduler_job" "reconciliation_tick" {
  name      = "paybridge-reconciliation-tick"
  region    = var.region
  schedule  = "*/15 * * * *"
  time_zone = "Etc/UTC"

  http_target {
    http_method = "POST"
    uri         = google_cloud_run_v2_service.reconciler.uri

    oidc_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}

output "cloud_run_url" {
  value = google_cloud_run_v2_service.reconciler.uri
}
