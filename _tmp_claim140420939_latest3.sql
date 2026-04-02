SELECT dr.generated_at,
       dr.recommendation::text,
       COALESCE(string_agg(COALESCE(e.value->>'code','') || ':' || COALESCE(e.value->>'name',''), ' | ' ORDER BY e.value->>'code'), '') AS triggered_codes
FROM decision_results dr
JOIN claims c ON c.id = dr.claim_id
LEFT JOIN LATERAL jsonb_array_elements(COALESCE(dr.decision_payload->'checklist', '[]'::jsonb)) e(value)
  ON COALESCE((e.value->>'triggered')::boolean, false) = true
WHERE c.external_claim_id = '140420939'
GROUP BY dr.generated_at, dr.recommendation
ORDER BY dr.generated_at DESC
LIMIT 3;
