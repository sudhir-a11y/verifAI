SELECT generated_at, recommendation::text, is_active
FROM decision_results dr
JOIN claims c ON c.id = dr.claim_id
WHERE c.external_claim_id='140420939' AND dr.generated_by='checklist_pipeline'
ORDER BY generated_at DESC
LIMIT 5;
