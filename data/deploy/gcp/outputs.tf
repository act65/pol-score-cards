output "bucket" {
  value       = google_storage_bucket.corpus.name
  description = "GCS bucket holding the source, corpus, and logs."
}

output "instance" {
  value       = google_compute_instance.scraper.name
  description = "The backfill VM (powers itself off when done)."
}

output "watch_progress" {
  description = "SSH in and tail the live log."
  value       = "gcloud compute ssh ${google_compute_instance.scraper.name} --zone ${var.zone} --command 'sudo tail -f /var/log/backfill.log'"
}

output "check_done" {
  description = "The VM writes a DONE marker to the bucket when finished."
  value       = "gsutil ls gs://${google_storage_bucket.corpus.name}/DONE"
}

output "download_corpus" {
  description = "Pull the finished corpus locally."
  value       = "gsutil -m rsync -r gs://${google_storage_bucket.corpus.name}/corpus ./corpus"
}
