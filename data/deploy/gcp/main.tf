terraform {
  required_version = ">= 1.3"
  required_providers {
    google  = { source = "hashicorp/google", version = "~> 5.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
    random  = { source = "hashicorp/random", version = "~> 3.5" }
  }
}

provider "google" {
  project = var.project
  region  = var.region
  zone    = var.zone
}

# Enable the APIs we touch (no-op if already on). IAM is needed to create the
# VM's service account; compute + storage for the VM and bucket.
resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "random_id" "suffix" {
  byte_length = 3
}

# ---------------------------------------------------------------------------
# Bucket: delivers the scraper source to the VM and receives the corpus back.
# ---------------------------------------------------------------------------
resource "google_storage_bucket" "corpus" {
  name                        = "${var.project}-pol-corpus-${random_id.suffix.hex}"
  location                    = var.region
  force_destroy               = true # `terraform destroy` wipes it — download first!
  uniform_bucket_level_access = true
  depends_on                  = [google_project_service.apis]
}

# Zip the scraper code (the data/ subproject) and upload it. The VM unzips +
# `docker build`s it. Excludes the big scraped dumps and the deploy dir itself.
data "archive_file" "src" {
  type        = "zip"
  source_dir  = "${path.module}/../.."
  output_path = "${path.module}/.pol_scraper_src.zip"
  excludes = [
    "data/**", "deploy/**", "**/__pycache__/**",
    "*.egg-info/**", ".pytest_cache/**", "*.zip",
  ]
}

resource "google_storage_bucket_object" "src" {
  name   = "src-${data.archive_file.src.output_md5}.zip"
  bucket = google_storage_bucket.corpus.name
  source = data.archive_file.src.output_path
}

# ---------------------------------------------------------------------------
# A dedicated, least-privilege service account for the VM: it only needs to
# read/write objects in this one bucket.
# ---------------------------------------------------------------------------
resource "google_service_account" "scraper" {
  account_id   = "pol-scraper-${random_id.suffix.hex}"
  display_name = "NZ pol scorecards backfill VM"
  depends_on   = [google_project_service.apis] # needs the IAM API enabled first
}

resource "google_storage_bucket_iam_member" "scraper_rw" {
  bucket = google_storage_bucket.corpus.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.scraper.email}"
}

# ---------------------------------------------------------------------------
# The VM. Debian 12 (gsutil preinstalled); startup script does everything and
# powers the box off when finished (cheap to leave; `terraform destroy` cleans up).
# ---------------------------------------------------------------------------
resource "google_compute_instance" "scraper" {
  name         = "pol-scraper-${random_id.suffix.hex}"
  machine_type = var.machine_type
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 30 # GB — room for the Playwright image + corpus
    }
  }

  network_interface {
    network = "default"
    access_config {} # ephemeral external IP for outbound scraping
  }

  service_account {
    email  = google_service_account.scraper.email
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = templatefile("${path.module}/startup-script.sh.tftpl", {
    bucket      = google_storage_bucket.corpus.name
    src_object  = google_storage_bucket_object.src.name
    since       = var.since
    until       = var.until
    only        = var.only
    skip        = var.skip
    delay       = var.delay
    hansard_max = var.hansard_max
    hf_repo     = var.hf_repo
    hf_token    = var.hf_token
  })

  # Let the VM tear itself down cleanly on `poweroff` without auto-restarting.
  scheduling {
    automatic_restart = false
  }

  depends_on = [google_storage_bucket_iam_member.scraper_rw]
}
