-- Add git_sha column (hermia-c38b provenance fix).
-- Idempotent — safe to run multiple times.
--
-- hermia_version reads frozen editable-install dist-info metadata, which
-- goes stale the moment a checkout moves to a different commit without a
-- reinstall. git_sha is stamped independently and freshly on every run, so
-- stale hermia_version data is self-diagnosing.

ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS git_sha TEXT;
