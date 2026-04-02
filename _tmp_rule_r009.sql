SELECT rule_id, name, decision, severity, priority, scope_json, conditions, remark_template
FROM openai_claim_rules
WHERE rule_id = 'R009';
