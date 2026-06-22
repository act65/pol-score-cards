# Run the backfill on GCP — one `terraform apply`

This spins up a throwaway GCP VM that runs the whole term backfill and drops the
corpus into a bucket (optionally pushing it to HuggingFace), then powers itself
off. You don't SSH in or run anything by hand.

```
data/deploy/gcp/
  main.tf · variables.tf · outputs.tf   # the module
  startup-script.sh.tftpl               # what the VM runs on boot
  terraform.tfvars.example              # copy → terraform.tfvars, set project
```

## What it does

1. Packages the scraper code (`data/`) and uploads it to a new GCS bucket.
2. Boots a Debian VM that installs Docker, builds `Dockerfile.scraper`, and runs
   `scripts/backfill.py` over `--since 2023-10-06 --until 2026-11-07` for every
   in-scope source (parties, RNZ + Newsroom + Spinoff, Parliament, Hansard).
3. Writes `manifest.json` + the dataset card, mirrors the corpus to
   `gs://<bucket>/corpus`, uploads the log, and writes a `DONE` marker.
4. `poweroff`s itself. A stopped VM costs only its disk (cents/day) until you
   `terraform destroy`.

## Prereqs (one-time)

- `terraform` and `gcloud` installed.
- `gcloud auth application-default login` (so Terraform can talk to GCP).
- A GCP project with billing enabled. (The module enables the Compute + Storage
  APIs for you.)

## Run it

```bash
cd data/deploy/gcp
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars          # set project = "..."  (optionally hf_repo/hf_token)

terraform init
terraform apply                   # ~1 min to create; the scrape then runs on the VM
```

`apply` returns immediately once the VM is created — the backfill runs on the box
for a while afterward (the browser sources + Hansard are the slow part; budget a
few hours). Watch or wait:

```bash
terraform output -raw watch_progress | bash     # tail the live log over SSH
gsutil ls gs://$(terraform output -raw bucket)/DONE   # exists once finished
```

## Collect the results

```bash
terraform output -raw download_corpus | bash    # → ./corpus (json per source + manifest.json + README.md)
```

If you set `hf_repo`/`hf_token`, it's already published at
`https://huggingface.co/datasets/<hf_repo>`. Otherwise push from your laptop:

```bash
cd ../..        # back to data/
python publish_corpus.py --corpus deploy/gcp/corpus --repo you/nz-pol-statements --push
```

## Re-running after a code fix

The VM bakes the scraper image from a zip uploaded at apply time, and only runs
its startup script on first boot. To pick up changed scraper code, **replace the
instance** — this re-uploads the source and re-runs the whole backfill:

```bash
terraform apply -replace="google_compute_instance.scraper"
```

## Known gotchas (seen on the first real run)

- **Some party sites 403 from datacenter IPs.** greens, opportunity (TOP), and
  maoriparty (Te Pāti Māori) sit behind Cloudflare and can reject GCP's IP even
  with a real browser UA. They scrape fine from a **residential** connection, and
  they're plain HTTP (fast, no browser). If they come back empty/403 in the VM
  run, just run them on your laptop and drop the files into the corpus:
  ```bash
  cd data/scrapers
  for s in greens top tpm; do python sources.py scrape --source $s --since 2023-10-06 --out ../corpus/$s.json; done
  ```
- **Some adapters can silently under-collect** if a site changes its article-URL
  scheme. National, for example, has used three slug formats over time
  (`260529-foo`, `20260521-foo`, bare `boost-for-law-and-order`); the adapter now
  matches any `/news/<slug>`. If a source's article count looks suspiciously low,
  check whether its listing links match the adapter's pattern before assuming the
  archive is shallow.
- **Browser sources** (rnz, labour, nzfirst, parliament, hansard) need the
  Playwright Chromium that ships *with the base image* — the Dockerfile no longer
  upgrades Playwright (a newer Chromium segfaults against the image's libs).

## Tear down

```bash
terraform destroy     # deletes the VM, bucket (force), and service account
```

`destroy` wipes the bucket — **download the corpus first** (or rely on the HF push).

## Knobs (in terraform.tfvars)

| Variable | Default | Notes |
|---|---|---|
| `machine_type` | `e2-standard-2` | 8 GB RAM is comfortable for headless Chromium. |
| `hansard_max` | `3000` | Hansard is the long pole; raise for fuller coverage, lower for a quick first run. |
| `skip` | `""` | e.g. `"hansard,parliament"` — the Radware-walled sources can fail under *headless* Chromium. If they come back empty, skip them here and run them once on a desktop with `--headless=False` (see `../../HANSARD_HOWTO.md`). |
| `hf_repo` / `hf_token` | `""` | Set both to publish to HuggingFace from the VM. The token lands in instance metadata — fine for a personal project; otherwise leave blank and push locally. |

## Cost

A few hours on an `e2-standard-2` plus a little egress and storage — on the order
of a coffee. Don't forget `terraform destroy` when you've got the data.
