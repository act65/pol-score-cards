variable "project" {
  type        = string
  description = "Your GCP project ID."
}

variable "region" {
  type        = string
  default     = "australia-southeast1" # Sydney — closest region to NZ
  description = "GCP region for the bucket + VM."
}

variable "zone" {
  type        = string
  default     = "australia-southeast1-a"
  description = "GCP zone for the VM."
}

variable "machine_type" {
  type        = string
  default     = "e2-standard-2" # 2 vCPU / 8 GB — comfortable for headless Chromium
  description = "VM size. Scraping is I/O-bound; RAM matters for the browser sources."
}

variable "since" {
  type        = string
  default     = "2023-10-06"
  description = "Backfill start date (election day 2023)."
}

variable "until" {
  type        = string
  default     = "2026-11-07"
  description = "Backfill end date (election day 2026)."
}

variable "only" {
  type        = string
  default     = ""
  description = "Comma-separated subset of sources to run (blank = all in-scope)."
}

variable "skip" {
  type        = string
  default     = ""
  description = "Comma-separated sources to skip (e.g. 'hansard,parliament' if the Radware wall blocks headless)."
}

variable "delay" {
  type        = number
  default     = 1.0
  description = "Seconds between requests (politeness)."
}

variable "hansard_max" {
  type        = number
  default     = 3000
  description = "Cap on Hansard sections (the long pole — raise for fuller coverage, lower for a faster first run)."
}

variable "hf_repo" {
  type        = string
  default     = ""
  description = "Optional HuggingFace dataset id (e.g. you/nz-pol-statements). Blank = skip the push; corpus still lands in the bucket."
}

variable "hf_token" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Optional HuggingFace write token. If set with hf_repo, the VM pushes the corpus to HuggingFace. NB it is stored in instance metadata."
}
