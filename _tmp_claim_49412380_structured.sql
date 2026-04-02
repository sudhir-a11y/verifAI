SELECT csd.updated_at,
       csd.claim_type,
       csd.diagnosis,
       csd.complaints,
       csd.findings,
       csd.recommendation,
       LEFT(COALESCE(csd.conclusion,''), 260) AS conclusion
FROM claim_structured_data csd
JOIN claims c ON c.id = csd.claim_id
WHERE c.external_claim_id='49412380'
ORDER BY csd.updated_at DESC
LIMIT 3;
