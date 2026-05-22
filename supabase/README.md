# Ladder — Supabase

Run migrations in order against your Supabase project:

1. `migrations/0001_init.sql` — tables + auth bootstrap trigger.
2. `migrations/0002_rls_policies.sql` — enable RLS + owner policies.
3. `migrations/0003_indexes.sql` — B-tree indexes.
4. `migrations/0004_match_function.sql` — `match_knowledge_nodes` RPC.

Later (once data exists):
- `0005_vault_functions.sql` — BYOK per-user key decryption.
- `0006_vector_index.sql` — ivfflat index on `knowledge_nodes.embedding`.

## Running via SQL editor

Paste each file into the Supabase SQL editor in order. The `handle_new_user`
trigger in `0001` handles `auth.users → public.users` propagation, so nothing
else is needed to enable signup.

## Running via CLI

```bash
supabase link --project-ref <ref>
supabase db push
```
