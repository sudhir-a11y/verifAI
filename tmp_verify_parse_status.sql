SELECT c.external_claim_id AS claim_id,
       cd.parse_status,
       COUNT(*) AS doc_count
FROM claims c
JOIN claim_documents cd ON cd.claim_id = c.id
WHERE c.id IN (
  '2d2fb4ba-9c9b-4f97-8933-6fc6bb260c31'::uuid,
  'c6d7313b-ca3d-499d-bdec-c111f2882933'::uuid,
  '41f86247-b360-44de-a87e-df885996d091'::uuid,
  '16475b93-658b-412e-9ef8-d767efbf9df2'::uuid,
  '0a08178e-7b06-45de-82e0-8c1db691280b'::uuid
)
GROUP BY c.external_claim_id, cd.parse_status
ORDER BY c.external_claim_id, cd.parse_status;
