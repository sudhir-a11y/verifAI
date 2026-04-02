SELECT c.id::text AS claim_uuid,
       c.external_claim_id,
       rv.created_at,
       LEFT(COALESCE(rv.report_markdown,''), 260) AS report_markdown
FROM report_versions rv
JOIN claims c ON c.id = rv.claim_id
WHERE COALESCE(rv.report_markdown,'') ILIKE '%Right Lower Limb Varicose Veins%'
   OR COALESCE(rv.report_markdown,'') ILIKE '%Visible dilated varicosities%'
ORDER BY rv.created_at DESC
LIMIT 30;
