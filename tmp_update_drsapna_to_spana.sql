BEGIN;

DROP TABLE IF EXISTS tmp_name_updates;
CREATE TEMP TABLE tmp_name_updates (
  table_name text,
  column_name text,
  data_type text,
  updated_rows bigint
);

DO $$
DECLARE
  r record;
  v_cnt bigint;
  v_updated bigint;
  v_sql text;
  v_skip_users_username boolean;
BEGIN
  SELECT EXISTS(SELECT 1 FROM users WHERE LOWER(username) = 'spana') INTO v_skip_users_username;

  FOR r IN
    SELECT c.table_schema, c.table_name, c.column_name, c.data_type
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.data_type IN ('text', 'character varying', 'character', 'json', 'jsonb')
      AND NOT (c.table_name = 'users' AND c.column_name = 'username' AND v_skip_users_username)
  LOOP
    v_sql := format(
      'SELECT count(*) FROM %I.%I WHERE %I IS NOT NULL AND lower(%I::text) LIKE ''%%drsapna%%''',
      r.table_schema, r.table_name, r.column_name, r.column_name
    );
    EXECUTE v_sql INTO v_cnt;

    IF v_cnt > 0 THEN
      IF r.data_type IN ('json', 'jsonb') THEN
        v_sql := format(
          'UPDATE %I.%I SET %I = regexp_replace(%I::text, ''(?i)drsapna'', ''spana'', ''g'')::%s WHERE %I IS NOT NULL AND lower(%I::text) LIKE ''%%drsapna%%''',
          r.table_schema, r.table_name, r.column_name, r.column_name, r.data_type, r.column_name, r.column_name
        );
      ELSE
        v_sql := format(
          'UPDATE %I.%I SET %I = regexp_replace(%I, ''(?i)drsapna'', ''spana'', ''g'') WHERE %I IS NOT NULL AND lower(%I::text) LIKE ''%%drsapna%%''',
          r.table_schema, r.table_name, r.column_name, r.column_name, r.column_name, r.column_name
        );
      END IF;

      EXECUTE v_sql;
      GET DIAGNOSTICS v_updated = ROW_COUNT;

      INSERT INTO tmp_name_updates(table_name, column_name, data_type, updated_rows)
      VALUES (r.table_name, r.column_name, r.data_type, v_updated);
    END IF;
  END LOOP;
END $$;

SELECT table_name, column_name, data_type, updated_rows
FROM tmp_name_updates
ORDER BY updated_rows DESC, table_name, column_name;

COMMIT;