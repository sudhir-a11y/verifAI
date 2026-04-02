SELECT rv.id,
       rv.created_at,
       rv.report_status,
       rv.created_by,
       LEFT(COALESCE(rv.report_markdown,''), 420) AS report_head
FROM report_versions rv
JOIN claims c ON c.id = rv.claim_id
WHERE c.external_claim_id='49412380'
ORDER BY rv.created_at DESC
LIMIT 10;
