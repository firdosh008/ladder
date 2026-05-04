 Subject: Tenant lqjlfuhucwgsxerulqlf — JWKS endpoint hangs (no response in 30s), Storage returns HTTP 544 — auth and storage degraded
  while other services on same project respond normally                                                                                 
                                                                                                                                      
  Project ref: lqjlfuhucwgsxerulqlf                                                                                                     
  Region: ap-northeast-1                                                                                                                
  Started: ~2026-05-04 06:20 IST (just before this ticket)
  Public status page: "All Systems Operational" — incident not rolled up                                                                
                                                                                                                                        
  ---                                                                                                                                   
  Symptom                                                                                                                               
                                                            
  Two endpoints on this tenant are degraded while the rest of the project responds normally:
                                                                                                                                        
  1. /auth/v1/.well-known/jwks.json hangs indefinitely — connection establishes (TLS handshake completes in ~136ms) but the server never
   sends response headers. Times out after 30s with no data received. Reproduced 3 consecutive times.                                   
  2. /storage/v1/object/... returns HTTP 544 in ~5.9s. 544 is non-standard / Supabase-specific.                                         
                                                                                                                                        
  Other services on the same project work fine:
                                                                                                                                        
  ┌───────────────────────────────────────────────┬────────────────────────┬─────────────────┐                                          
  │                   Endpoint                    │         Status         │      Time       │
  ├───────────────────────────────────────────────┼────────────────────────┼─────────────────┤                                          
  │ /auth/v1/health                               │ 401 (expected w/o key) │ 181ms           │
  ├───────────────────────────────────────────────┼────────────────────────┼─────────────────┤
  │ /rest/v1/                                     │ 401 (expected w/o key) │ 148ms           │                                          
  ├───────────────────────────────────────────────┼────────────────────────┼─────────────────┤

  Project ref: lqjlfuhucwgsxerulqlf
  Region: ap-northeast-1
  Started: ~2026-05-04 06:20 IST (just before this ticket)
  Public status page: "All Systems Operational" — incident not rolled up

  ---
  Symptom

  Two endpoints on this tenant are degraded while the rest of the project responds normally:

  1. /auth/v1/.well-known/jwks.json hangs indefinitely — connection establishes (TLS handshake completes in ~136ms) but the server never
   sends response headers. Times out after 30s with no data received. Reproduced 3 consecutive times.
  2. /storage/v1/object/... returns HTTP 544 in ~5.9s. 544 is non-standard / Supabase-specific.

  Other services on the same project work fine:

  ┌───────────────────────────────────────────────┬────────────────────────┬─────────────────┐
  │                   Endpoint                    │         Status         │      Time       │
  ├───────────────────────────────────────────────┼────────────────────────┼─────────────────┤
  │ /auth/v1/health                               │ 401 (expected w/o key) │ 181ms           │
  ├───────────────────────────────────────────────┼────────────────────────┼─────────────────┤
  │ /rest/v1/                                     │ 401 (expected w/o key) │ 148ms           │
  ├───────────────────────────────────────────────┼────────────────────────┼─────────────────┤
  │ /realtime/v1/api/health                       │ 401 (expected w/o key) │ 132ms           │
  ├───────────────────────────────────────────────┼────────────────────────┼─────────────────┤
  │ /auth/v1/.well-known/jwks.json                │ 000                    │ 30s timeout × 3 │
  ├───────────────────────────────────────────────┼────────────────────────┼─────────────────┤
  │ /storage/v1/object/public/excalidraw_scenes/x │ 544                    │ 5.9s            │
  └───────────────────────────────────────────────┴────────────────────────┴─────────────────┘

  Reproduction (from my dev machine):

  SUPABASE_URL="https://lqjlfuhucwgsxerulqlf.supabase.co"

  # Hangs — never returns
  curl -v --max-time 30 "$SUPABASE_URL/auth/v1/.well-known/jwks.json"

  # Returns 544
  curl -v --max-time 10 "$SUPABASE_URL/storage/v1/object/public/excalidraw_scenes/missing.txt"

  Related log line from my dashboard logs:

  lqjlfuhucwgsxerulqlf | GET | ABORTED REQ | 10.101.11.191 | req-58yu |
  /tenants/lqjlfuhucwgsxerulqlf/health | @supabase-infra/mgmt-api/9bfca14
  host: storage-api-canary-lb-ap-northeast-1-adm.supabase.co

  This is your internal canary aborting a tenant health check — same window as the user-facing failures.                                
   
  Impact                                                                                                                                
                                                            
  - All authenticated REST/WebSocket calls in our backend fail with httpx.ReadTimeout because the auth middleware blocks waiting for    
  JWKS public keys.
  - Cannot verify any user JWTs → users can't log in.                                                                                   
  - Storage uploads/reads return 544 → can't persist or fetch scene artifacts.                                                          
                                                                                                                                        
  Asks                                                                                                                                  
                                                                                                                                        
  1. Investigate JWKS service health for tenant lqjlfuhucwgsxerulqlf.                                                                   
  2. Investigate storage service health for the same tenant (HTTP 544 with the canary ABORT log above).
  3. ETA to recovery, or any workaround for JWKS while it's degraded.                                                                   
                                                                                                                                        
  What is not causing this (already eliminated):                                                                                        
                                                                                                                                        
  - Not local network (DNS 38ms, TCP 80ms, TLS 136ms — handshake fine)                                                                  
  - Not other Supabase services (auth /health, REST, Realtime all respond in <200ms on the same project)
  - Not regional outage (ap-northeast-1 reports operational)                                                                            
  - Not application code (no recent changes to auth middleware, no recent storage policy changes)                                       
                                                                                                                                        
  ---                                                                                                                                   
  Tips for filing it:                                                                                                                   
                                                                                                                                        
  1. Open at https://supabase.com/dashboard/support/new
  2. Pick category: "Performance" or "Service unavailable" if available, otherwise "Other"                                              
  3. Include the project ref lqjlfuhucwgsxerulqlf in the project picker                                                                 
  4. Set severity: if you're on a paid plan, mark it "Urgent / production down" — this is genuinely auth-down so it qualifies           
  5. Add the request ID req-58yu somewhere visible — it gives them a starting point in their logs                                       
                                                                                                                                        
  Once it's filed, paste me the ticket number and I'll include it in our session notes if you keep working.                             
                                                                                                              