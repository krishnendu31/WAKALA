"""Phase 5 adversarial security benchmark, performance measurement and evidence.

Everything here runs in ISOLATED, temporary environments (in-memory or
temporary-file SQLite, freshly generated development keys, per-run in-memory
officer passwords). Nothing reads or writes the server's database or the
development keystore. Results are what the real gateway/officer code returned;
no outcome is hard-coded. Synthetic prototype benchmark — not production
government statistics.
"""
