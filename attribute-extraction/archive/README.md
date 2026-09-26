# Superseded scripts

Kept rather than deleted: these document how the published output was
produced, and several are the only record of a migration's mechanics. None is
on a current path — nothing in the pipeline imports them, and no test covers
them. Run them only to understand history.

| script | superseded by | why |
|---|---|---|
| `build_site_data.py` | `build_v2_dataset.py` | v1 bundler (Jun 20), pre-bias-adjustment |
| `resume_extraction.py` | `overnight_run.py` + the systemd units | hardcodes the 3-month / full-term v2.0 runs |
| `publish_v2_dataset.py` | *(unreplaced)* | v2.0 HuggingFace publisher; a v3 release wants `data/publish_corpus.py`'s shape |
| `start_at.py` | `nz-scorecards-nightly.service` | ad-hoc scheduler; systemd survives a reboot, this did not |
| `usage_report.py` | `quota_budget.py status` | read the old usage log format |
| `clean_site_ids.py` | — | one-off id repair, already applied |
| `benchmark_diarization.py` | — | one-off speaker-attribution benchmark; result in `bench_diar.json` |

Two of these describe scores that are **retired**: v2.0 used a different
Civility scale and an attribute that no longer exists, so anything they
rebuild is not comparable with what the site serves. See `../ATTRIBUTES.md`.
