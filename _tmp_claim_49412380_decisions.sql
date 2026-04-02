SELECT dr.id,
       dr.generated_at,
       dr.recommendation::text,
       dr.route_target,
       dr.is_active,
       LEFT(COALESCE(dr.explanation_summary,''), 320) AS explanation_summary
FROM decision_results dr
JOIN claims c ON c.id = dr.claim_id
WHERE c.external_claim_id='49412380'
ORDER BY dr.generated_at DESC
LIMIT 10;
