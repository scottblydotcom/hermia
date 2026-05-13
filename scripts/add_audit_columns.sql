ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS raw_prompt TEXT;
ALTER TABLE hermia_results ADD COLUMN IF NOT EXISTS raw_response TEXT;
