-- Storage bucket for `.excalidraw` JSON envelopes.
--
-- Public read so the bucket-hosted URL can be passed to
-- `excalidraw.com/#url=<encoded>` (PRD §5.5). Writes go through the
-- backend which uses the service role key and pins the upload path to
-- `<auth.uid()>/<session_id>/<random>.excalidraw`. The path-prefix RLS
-- policy below ensures even direct anon uploads (if any are ever
-- attempted) cannot land outside the caller's namespace.

INSERT INTO storage.buckets (id, name, public)
VALUES ('excalidraw_scenes', 'excalidraw_scenes', true)
ON CONFLICT (id) DO UPDATE SET public = EXCLUDED.public;

-- Authenticated users may write only into their own folder.
CREATE POLICY "scene_owner_write"
  ON storage.objects
  FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'excalidraw_scenes'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "scene_owner_update"
  ON storage.objects
  FOR UPDATE
  TO authenticated
  USING (
    bucket_id = 'excalidraw_scenes'
    AND (storage.foldername(name))[1] = auth.uid()::text
  )
  WITH CHECK (
    bucket_id = 'excalidraw_scenes'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "scene_owner_delete"
  ON storage.objects
  FOR DELETE
  TO authenticated
  USING (
    bucket_id = 'excalidraw_scenes'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

-- Public read — required for excalidraw.com to fetch the JSON.
CREATE POLICY "scene_public_read"
  ON storage.objects
  FOR SELECT
  TO anon, authenticated
  USING (bucket_id = 'excalidraw_scenes');
