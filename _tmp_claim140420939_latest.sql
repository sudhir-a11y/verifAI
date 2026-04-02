WITH latest AS (
  SELECT dr.*
  FROM decision_results dr
  JOIN claims c ON c.id = dr.claim_id
  WHERE c.external_claim_id = '140420939'
  ORDER BY dr.generated_at DESC
  LIMIT 1
)
SELECT l.id,
       l.generated_at,
       l.recommendation::text AS recommendation,
       l.route_target,
       l.manual_review_required,
       l.review_priority,
       COALESCE(string_agg(COALESCE(e.value->>'code','') || ':' || COALESCE(e.value->>'name',''), ' | ' ORDER BY e.value->>'code'), '') AS triggered_codes,
       LEFT(COALESCE(l.explanation_summary,''), 300) AS explanation_summary,
       LEFT(COALESCE(l.decision_payload->>'conclusion',''), 300) AS payload_conclusion,
       LEFT(COALESCE(l.decision_payload->'source_summary'->'reporting'->>'recommendation_text',''), 220) AS reporting_recommendation_text
FROM latest l
LEFT JOIN LATERAL jsonb_array_elements(COALESCE(l.decision_payload->'checklist', '[]'::jsonb)) e(value) ON true
  AND COALESCE((e.value->>'triggered')::boolean, false) = true
GROUP BY l.id, l.generated_at, l.recommendation, l.route_target, l.manual_review_required, l.review_priority, l.explanation_summary, l.decision_payload;
