-- Per-idea preferred runtime in minutes.
--
-- Set when the user picks a duration from /make's research tile dropdown
-- (and, on day 2, from the content_extract analyzer's `derived_duration_min`).
-- Used by the Studio crew as the script_writer's target duration when no
-- explicit override is passed in the WS URL.
--
-- Nullable on purpose: ideas created before this column existed (or
-- manually-added ideas with no opinion on length) leave it null, and the
-- Studio crew falls back to its 20-minute default.
ALTER TABLE ideas
  ADD COLUMN target_duration_min int
    CHECK (target_duration_min IS NULL OR target_duration_min BETWEEN 3 AND 60);
