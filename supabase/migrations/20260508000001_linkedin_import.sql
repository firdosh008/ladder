-- Rename linkedin_scraped_at to linkedin_imported_at — the column now covers
-- both URL scraping and JSON export import flows.
ALTER TABLE user_profiles RENAME COLUMN linkedin_scraped_at TO linkedin_imported_at;
