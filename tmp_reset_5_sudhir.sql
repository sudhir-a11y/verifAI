BEGIN;

CREATE TEMP TABLE target_claims (claim_id UUID PRIMARY KEY);
INSERT INTO target_claims (claim_id) VALUES
('2d2fb4ba-9c9b-4f97-8933-6fc6bb260c31'),
('c6d7313b-ca3d-499d-bdec-c111f2882933'),
('41f86247-b360-44de-a87e-df885996d091'),
('16475b93-658b-412e-9ef8-d767efbf9df2'),
('0a08178e-7b06-45de-82e0-8c1db691280b');

-- remove QC labels/upload mapping and generated artifacts
DELETE FROM feedback_labels fl USING target_claims t WHERE fl.claim_id = t.claim_id;
DELETE FROM report_versions rv USING target_claims t WHERE rv.claim_id = t.claim_id;
DELETE FROM decision_results dr USING target_claims t WHERE dr.claim_id = t.claim_id;
DELETE FROM document_extractions de USING target_claims t WHERE de.claim_id = t.claim_id;
DELETE FROM claim_report_uploads cru USING target_claims t WHERE cru.claim_id = t.claim_id;

-- reset document parse markers so pipeline can run fresh
UPDATE claim_documents cd
SET parse_status = 'pending',
    parsed_at = NULL
FROM target_claims t
WHERE cd.claim_id = t.claim_id;

-- keep assigned to sudhir and make claims active for fresh processing
UPDATE claims c
SET assigned_doctor_id = 'sudhir',
    status = 'in_review'
FROM target_claims t
WHERE c.id = t.claim_id;

COMMIT;

-- verification snapshot
SELECT
  c.external_claim_id AS claim_id,
  c.id::text AS claim_uuid,
  c.status,
  c.assigned_doctor_id,
  (SELECT COUNT(*) FROM claim_documents d WHERE d.claim_id=c.id) AS docs,
  (SELECT COUNT(*) FROM document_extractions de WHERE de.claim_id=c.id) AS extractions,
  (SELECT COUNT(*) FROM decision_results dr WHERE dr.claim_id=c.id) AS decisions,
  (SELECT COUNT(*) FROM report_versions rv WHERE rv.claim_id=c.id) AS reports,
  (SELECT COUNT(*) FROM feedback_labels fl WHERE fl.claim_id=c.id) AS feedback_labels,
  (SELECT COUNT(*) FROM claim_report_uploads cru WHERE cru.claim_id=c.id) AS upload_rows
FROM claims c
JOIN target_claims t ON t.claim_id = c.id
ORDER BY c.external_claim_id;
