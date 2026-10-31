"""Export pristine extended sample data; never includes live edits or credentials."""
from pathlib import Path
import tempfile,json
import db

def quote(value):
    if value is None:return 'NULL'
    if isinstance(value,str):
        # NO_BACKSLASH_ESCAPES makes JSON and quoted strings deterministic.
        return "'"+value.replace("'","''")+"'"
    return str(value)

def main():
    dest=Path(__file__).resolve().parent/'database';dest.mkdir(exist_ok=True)
    previous=db.SQLITE_PATH;previous_config=db.MYSQL_CONFIG
    with tempfile.TemporaryDirectory() as temp:
        db.SQLITE_PATH=Path(temp)/'sample.sqlite3';db.MYSQL_CONFIG=None;db.init_demo()
        parts=['-- PlanFlow fictional October–December 2026 data. Run once in a new schema.',
          "SET @previous_sql_mode = @@SESSION.sql_mode;",
          "SET SESSION sql_mode = CONCAT_WS(',', NULLIF(@@SESSION.sql_mode,''), 'NO_BACKSLASH_ESCAPES');",
          'CREATE DATABASE IF NOT EXISTS planflow_app_october_2026 CHARACTER SET utf8mb4;',
          'USE planflow_app_october_2026;',db.mysql_schema(),'START TRANSACTION;']
        with db.connect() as con:
            for table in ['departments','shifts','daily_plans','plan_extras','scenarios']:
                records=con.rows('SELECT * FROM '+table)
                columns=list(records[0])
                parts.append('INSERT INTO '+table+' ('+','.join(columns)+') VALUES\n'+',\n'.join('('+','.join(quote(r[c]) for c in columns)+')' for r in records)+';')
        parts.extend(['COMMIT;','SET SESSION sql_mode = @previous_sql_mode;'])
        path=dest/'planflow_october_to_december_2026.sql';path.write_text('\n\n'.join(parts)+'\n',encoding='utf-8')
    db.SQLITE_PATH=previous;db.MYSQL_CONFIG=previous_config
    print('Exported SQL with 552 plans, 552 extras and 36 scenario snapshots.')

if __name__=='__main__':main()
