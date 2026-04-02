WITH base AS (
  SELECT c.id,
         c.external_claim_id,
         c.status,
         c.assigned_doctor_id,
         c.created_at,
         COUNT(DISTINCT d.id) AS docs,
         COUNT(DISTINCT de.id) AS extractions,
         COUNT(DISTINCT rv.id) AS reports,
         COUNT(DISTINCT dr.id) AS decisions
  FROM claims c
  LEFT JOIN claim_documents d ON d.claim_id = c.id
  LEFT JOIN document_extractions de ON de.document_id = d.id
  LEFT JOIN report_versions rv ON rv.claim_id = c.id
  LEFT JOIN decision_results dr ON dr.claim_id = c.id
  WHERE lower(replace(coalesce(c.assigned_doctor_id,''),' ','')) LIKE '%sudhir%'
    AND c.status <> 'withdrawn'
  GROUP BY c.id, c.external_claim_id, c.status, c.assigned_doctor_id, c.created_at
)
SELECT id::text AS claim_uuid,
       external_claim_id AS claim_id,
       status,
       assigned_doctor_id,
       to_char(created_at,'YYYY-MM-DD HH24:MI') AS created_at,
       docs, extractions, reports, decisions
FROM base
WHERE docs > 0
ORDER BY extractions DESC, reports DESC, decisions DESC, created_at DESC
LIMIT 5;
