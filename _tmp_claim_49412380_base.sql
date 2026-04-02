SELECT c.id::text AS claim_uuid,
       c.external_claim_id,
       c.status::text,
       c.assigned_doctor_id,
       c.updated_at
FROM claims c
WHERE c.external_claim_id = '49412380';
