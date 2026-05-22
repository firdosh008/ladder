-- Add fractional position column for manual kanban ordering.
ALTER TABLE ideas ADD COLUMN position double precision;

-- Backfill existing rows per (user_id, status), ordered by current default sort.
UPDATE ideas i
SET position = sub.rn * 1000
FROM (
  SELECT id,
         row_number() OVER (
           PARTITION BY user_id, status
           ORDER BY opportunity_score DESC NULLS LAST, created_at DESC
         ) AS rn
  FROM ideas
) sub
WHERE i.id = sub.id;

CREATE INDEX IF NOT EXISTS ideas_user_status_position_idx
  ON ideas (user_id, status, position);
