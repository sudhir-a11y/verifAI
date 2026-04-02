SELECT c.id::text AS claim_uuid,
       c.external_claim_id,
       dr.generated_at,
       dr.recommendation::text AS recommendation,
       LEFT(COALESCE(dr.explanation_summary,''), 260) AS explanation_summary
FROM decision_results dr
JOIN claims c ON c.id = dr.claim_id
WHERE COALESCE(dr.explanation_summary,'') ILIKE '%Right Lower Limb Varicose Veins%'
   OR COALESCE(dr.explanation_summary,'') ILIKE '%Visible dilated varicosities%'
ORDER BY dr.generated_at DESC
LIMIT 30;
