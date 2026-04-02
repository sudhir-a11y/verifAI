SELECT 'ec2.users.spana='||COUNT(*) FROM users WHERE LOWER(username)='spana';
SELECT 'ec2.users.drsapna='||COUNT(*) FROM users WHERE LOWER(username)='drsapna';
SELECT 'ec2.claims.assigned.spana='||COUNT(*) FROM claims WHERE LOWER(COALESCE(assigned_doctor_id,'')) LIKE '%spana%';