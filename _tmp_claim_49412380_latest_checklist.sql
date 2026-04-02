WITH latest AS (
  SELECT dr.*
  FROM decision_results dr
  JOIN claims c ON c.id = dr.claim_id
  WHERE c.external_claim_id='49412380'
  ORDER BY dr.generated_at DESC
  LIMIT 1
)
SELECT l.generated_at,
       l.recommendation::text,
       e.value->>'code' AS code,
       e.value->>'name' AS name,
       e.value->>'triggered' AS triggered,
       e.value->>'note' AS note
FROM latest l
LEFT JOIN LATERAL jsonb_array_elements(COALESCE(l.decision_payload->'checklist', '[]'::jsonb)) e(value) ON true
ORDER BY code;
