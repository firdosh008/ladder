-- LinkedIn profile integration
ALTER TABLE user_profiles ADD COLUMN linkedin_url text;
ALTER TABLE user_profiles ADD COLUMN linkedin_scraped_at timestamptz;
