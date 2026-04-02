SELECT dr.id,
       dr.generated_at,
       dr.recommendation::text,
       dr.route_target,
       dr.manual_review_required,
       dr.review_priority,
       dr.rule_hits,
       dr.explanation_summary,
       dr.decision_payload
FROM decision_results dr
JOIN claims c ON c.id = dr.claim_id
WHERE c.external_claim_id = '140420939'
ORDER BY dr.generated_at DESC
LIMIT 3;
