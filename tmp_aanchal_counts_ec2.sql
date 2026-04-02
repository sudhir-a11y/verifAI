SELECT 'claims.assigned_doctor_id.aanchal='||COUNT(*) AS v
FROM claims
WHERE LOWER(COALESCE(assigned_doctor_id,'')) LIKE '%aanchal%';

SELECT 'report_versions.created_by.aanchal='||COUNT(*) AS v
FROM report_versions
WHERE LOWER(COALESCE(created_by,''))='aanchal';

SELECT 'auth_logs.username.aanchal='||COUNT(*) AS v
FROM auth_logs
WHERE LOWER(COALESCE(username,''))='aanchal';