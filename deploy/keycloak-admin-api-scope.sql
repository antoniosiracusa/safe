-- Keycloak >= 26.8: l'Admin REST API accetta solo token con l'audience dell'API di amministrazione, fornita dallo
-- scope "kc-admin-api" (creato dalla migrazione). Il client di servizio "safe-admin", usato dal portale per inviti e
-- disattivazioni, deve averlo tra gli scope predefiniti, altrimenti riceve 401.
-- Nelle installazioni nuove lo scope è già nel realm (infra/keycloak/realm-safe.json); questo script serve ai realm
-- creati con versioni precedenti. Da eseguire sul database "keycloak" dopo il primo avvio della nuova versione,
-- poi riavviare Keycloak (la configurazione dei client è in cache). Idempotente.
INSERT INTO client_scope_client (client_id, scope_id, default_scope)
SELECT c.id, s.id, true
FROM client c
JOIN realm r ON r.id = c.realm_id
JOIN client_scope s ON s.realm_id = r.id AND s.name = 'kc-admin-api'
WHERE r.name = 'safe' AND c.client_id = 'safe-admin'
ON CONFLICT DO NOTHING;
