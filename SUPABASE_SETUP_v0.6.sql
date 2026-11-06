-- DataMendry v0.6: run only in YOUR Supabase project's SQL Editor.
-- Storage bucket MUST be private, and access is scoped to auth.uid().
-- Create bucket through Storage UI: name = datamendry-files; Public = OFF;
-- set max upload size to 8 MB. Then run these policies.

CREATE POLICY "datamendry_read_own_csv" ON storage.objects
  FOR SELECT TO authenticated
  USING (bucket_id = 'datamendry-files'
    AND (storage.foldername(name))[1] = (SELECT auth.uid())::text);

CREATE POLICY "datamendry_insert_own_csv" ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (bucket_id = 'datamendry-files'
    AND (storage.foldername(name))[1] = (SELECT auth.uid())::text);

CREATE POLICY "datamendry_delete_own_csv" ON storage.objects
  FOR DELETE TO authenticated
  USING (bucket_id = 'datamendry-files'
    AND (storage.foldername(name))[1] = (SELECT auth.uid())::text);

-- No UPDATE policy: users cannot overwrite a saved object.
-- Storage objects already have RLS enabled in Supabase; do not disable it.
