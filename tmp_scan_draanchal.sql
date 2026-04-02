DROP TABLE IF EXISTS tmp_draanchal_scan;
CREATE TEMP TABLE tmp_draanchal_scan (
  table_name text,
  column_name text,
  data_type text,
  matched_rows bigint
);

DO $$
DECLARE
  r record;
  v_cnt bigint;
  v_sql text;
BEGIN
  FOR r IN
    SELECT c.table_schema, c.table_name, c.column_name, c.data_type
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.data_type IN ('text', 'character varying', 'character', 'json', 'jsonb')
  LOOP
    v_sql := format(
      'SELECT count(*) FROM %I.%I WHERE %I IS NOT NULL AND lower(%I::text) LIKE ''%%draanchal%%''',
      r.table_schema, r.table_name, r.column_name, r.column_name
    );
    EXECUTE v_sql INTO v_cnt;
    IF v_cnt > 0 THEN
      INSERT INTO tmp_draanchal_scan(table_name, column_name, data_type, matched_rows)
      VALUES (r.table_name, r.column_name, r.data_type, v_cnt);
    END IF;
  END LOOP;
END $$;

SELECT table_name, column_name, data_type, matched_rows
FROM tmp_draanchal_scan
ORDER BY matched_rows DESC, table_name, column_name;