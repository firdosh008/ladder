-- Per-session brand color override.
--
-- Header pill is a color picker rather than a brand record selector — the
-- founder picks a hex and the scene crew uses it as the primary accent for
-- generated Excalidraw drawings. This is intentionally lighter-weight than
-- creating a `brands` row per session.
--
-- Stored as a 7-char hex string (e.g. '#E8442A'); the route validates the
-- shape before write. NULL means "no override → fall back to PRD default".

ALTER TABLE studio_sessions
  ADD COLUMN IF NOT EXISTS brand_color text;
