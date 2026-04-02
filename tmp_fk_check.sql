SELECT
  conrelid::regclass AS table_name,
  conname,
  confrelid::regclass AS references_table
FROM pg_constraint
WHERE contype='f'
  AND (conrelid::regclass::text IN ('report_versions','decision_results','document_extractions','claim_documents','workflow_events','feedback_labels','claim_report_uploads')
       OR confrelid::regclass::text IN ('report_versions','decision_results','document_extractions','claim_documents','claims'))
ORDER BY 1,2;
