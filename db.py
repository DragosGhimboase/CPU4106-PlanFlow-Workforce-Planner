"""SQLite demo and MySQL use the same application interface."""
from pathlib import Path
from contextlib import contextmanager
import sqlite3, threading, re, json
from data import DEPARTMENTS, SHIFTS, PLAN_COLUMNS, EXTRA_COLUMNS, sample_data

ROOT=Path(__file__).resolve().parent
LOCAL=ROOT/'.local'
SQLITE_PATH=LOCAL/'planflow.sqlite3'
MYSQL_CONFIG=None
STATE_LOCK=threading.RLock()

SCHEMA='''
CREATE TABLE departments (department_id INTEGER PRIMARY KEY, department_name VARCHAR(50) NOT NULL UNIQUE);
CREATE TABLE shifts (shift_id INTEGER PRIMARY KEY, shift_name VARCHAR(30) NOT NULL UNIQUE, start_time VARCHAR(8) NOT NULL, end_time VARCHAR(8) NOT NULL);
CREATE TABLE daily_plans (
 plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
 plan_date VARCHAR(10) NOT NULL,
 department_id INTEGER NOT NULL REFERENCES departments(department_id),
 shift_id INTEGER NOT NULL REFERENCES shifts(shift_id),
 forecast_cases INTEGER NOT NULL CHECK(forecast_cases>=0),
 available_staff INTEGER NOT NULL CHECK(available_staff>=0),
 cases_per_person_hour DECIMAL(8,2) NOT NULL CHECK(cases_per_person_hour>0),
 productive_hours DECIMAL(4,2) NOT NULL CHECK(productive_hours>0 AND productive_hours<=12),
 notes VARCHAR(200) NOT NULL DEFAULT '',
 version INTEGER NOT NULL DEFAULT 1,
 UNIQUE(plan_date,department_id,shift_id));
CREATE TABLE plan_extras (
 plan_id INTEGER PRIMARY KEY REFERENCES daily_plans(plan_id),
 scheduled_staff INTEGER NOT NULL CHECK(scheduled_staff>=0),
 absent_staff INTEGER NOT NULL CHECK(absent_staff>=0 AND absent_staff<=scheduled_staff),
 paid_hours DECIMAL(4,2) NOT NULL CHECK(paid_hours>0 AND paid_hours<=12),
 overtime_hours DECIMAL(4,2) NOT NULL CHECK(overtime_hours>=0 AND overtime_hours<=4),
 hourly_cost DECIMAL(8,2) NOT NULL CHECK(hourly_cost>=0),
 overtime_rate DECIMAL(8,2) NOT NULL CHECK(overtime_rate>=0),
 dispatch_deadline VARCHAR(20) NOT NULL,
 actual_cases INTEGER CHECK(actual_cases>=0),
 actual_staff INTEGER CHECK(actual_staff>=0),
 actual_productive_hours DECIMAL(4,2) CHECK(actual_productive_hours>0 AND actual_productive_hours<=12),
 actual_finished_at VARCHAR(20));
CREATE TABLE scenarios (
 scenario_id INTEGER PRIMARY KEY AUTOINCREMENT,
 scenario_name VARCHAR(100) NOT NULL,
 plan_date VARCHAR(10) NOT NULL,
 shift_id INTEGER NOT NULL REFERENCES shifts(shift_id),
 created_at VARCHAR(25) NOT NULL,
 base_json TEXT NOT NULL,
 proposed_json TEXT NOT NULL,
 result_json TEXT NOT NULL);
CREATE TABLE audit_log (
 audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
 changed_at VARCHAR(25) NOT NULL,
 action VARCHAR(40) NOT NULL,
 entity_id INTEGER NOT NULL,
 before_json TEXT NOT NULL,
 after_json TEXT NOT NULL);
'''

def mysql_schema():
    text=SCHEMA.replace('INTEGER PRIMARY KEY AUTOINCREMENT','INT PRIMARY KEY AUTO_INCREMENT').replace('INTEGER','INT')
    text=re.sub(r'(department_id|shift_id|plan_id) INT (NOT NULL )?REFERENCES (\w+)\((\w+)\)',r'\1 INT \2',text)
    # MySQL does not enforce inline REFERENCES; declare explicit table foreign keys.
    text=text.replace('UNIQUE(plan_date,department_id,shift_id)', 'FOREIGN KEY(department_id) REFERENCES departments(department_id), FOREIGN KEY(shift_id) REFERENCES shifts(shift_id), UNIQUE(plan_date,department_id,shift_id)')
    text=text.replace('plan_id INT PRIMARY KEY REFERENCES daily_plans(plan_id)', 'plan_id INT PRIMARY KEY')
    text=text.replace('actual_finished_at VARCHAR(20))','actual_finished_at VARCHAR(20), FOREIGN KEY(plan_id) REFERENCES daily_plans(plan_id))')
    text=text.replace('result_json TEXT NOT NULL)', 'result_json TEXT NOT NULL, FOREIGN KEY(shift_id) REFERENCES shifts(shift_id))')
    return text

class Connection:
    def __init__(self,raw,mysql):self.raw=raw;self.mysql=mysql
    def execute(self,sql,args=()):
        cur=self.raw.cursor();cur.execute(sql.replace('?','%s') if self.mysql else sql,args);return cur
    def rows(self,sql,args=()):
        cur=self.execute(sql,args);result=[dict(x) for x in cur.fetchall()];cur.close();return result
    def one(self,sql,args=()):
        cur=self.execute(sql,args);row=cur.fetchone();cur.close();return dict(row) if row else None

@contextmanager
def connect():
    with STATE_LOCK:
        config=dict(MYSQL_CONFIG) if MYSQL_CONFIG else None
    if config:
        import pymysql
        raw=pymysql.connect(**config,charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor,autocommit=False,connect_timeout=5)
    else:
        raw=sqlite3.connect(SQLITE_PATH,timeout=15);raw.row_factory=sqlite3.Row;raw.execute('PRAGMA foreign_keys=ON')
    con=Connection(raw,bool(config))
    try:yield con;raw.commit()
    except Exception:raw.rollback();raise
    finally:raw.close()

def seed(con):
    plans,extras=sample_data()
    for r in DEPARTMENTS:con.execute('INSERT INTO departments VALUES (?,?)',r)
    for r in SHIFTS:con.execute('INSERT INTO shifts VALUES (?,?,?,?)',r)
    for r in plans:con.execute('INSERT INTO daily_plans ('+','.join(PLAN_COLUMNS)+') VALUES ('+','.join('?' for _ in r)+')',r)
    for r in extras:con.execute('INSERT INTO plan_extras ('+','.join(EXTRA_COLUMNS)+') VALUES ('+','.join('?' for _ in r)+')',r)
    seed_scenarios(con)

def seed_scenarios(con):
    from logic import calculate, summary
    for month,day in [(m,d) for m in (10,11,12) for d in (8,12,16,20,24,28)]:
        dt=f'2026-{month:02}-{day:02}'
        base=[calculate(r) for r in con.rows(PLAN_SELECT+' WHERE p.plan_date=? AND p.shift_id=1 ORDER BY p.department_id',(dt,))]
        for name,cover in [('Cover forecast',True),('One fewer staff per department',False)]:
            if con.one('SELECT scenario_id FROM scenarios WHERE plan_date=? AND shift_id=1 AND scenario_name=?',(dt,name)):continue
            proposed=[]
            for r in base:
                staff=r['required_staff'] if cover else max(0,r['available_staff']-1)
                result=calculate(r,staff,0);result.update(available_staff=staff,overtime_hours=0);proposed.append(result)
            serial=lambda v:json.dumps(v,default=lambda x:float(x))
            con.execute('INSERT INTO scenarios (scenario_name,plan_date,shift_id,created_at,base_json,proposed_json,result_json) VALUES (?,?,?,?,?,?,?)',
                (name,dt,1,dt+'T05:55:00',serial(base),serial(proposed),serial({'base_summary':summary(base),'proposed_summary':summary(proposed)})))

def extend_sample_data(con):
    """Add missing November/December keys; never overwrite a user's plan."""
    plans,extras=sample_data()
    existing={(r['plan_date'],r['department_id'],r['shift_id']) for r in con.rows('SELECT plan_date,department_id,shift_id FROM daily_plans')}
    added=0
    for plan,extra in zip(plans,extras):
        if plan[0]<'2026-11-01' or tuple(plan[:3]) in existing:continue
        cursor=con.execute('INSERT INTO daily_plans ('+','.join(PLAN_COLUMNS)+') VALUES ('+','.join('?' for _ in plan)+')',plan)
        plan_id=cursor.lastrowid;cursor.close()
        linked=(plan_id,*extra[1:])
        con.execute('INSERT INTO plan_extras ('+','.join(EXTRA_COLUMNS)+') VALUES ('+','.join('?' for _ in linked)+')',linked)
        added+=1
    return added

def init_demo():
    LOCAL.mkdir(exist_ok=True)
    with connect() as con:
        if con.one("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_plans'"):
            extend_sample_data(con);seed_scenarios(con);return
        con.raw.executescript(SCHEMA);seed(con)

def configure_mysql(host,port,user,password):
    """Create only our fixed dedicated schema, never overwrite unrelated tables."""
    import pymysql
    global MYSQL_CONFIG
    if host not in ('localhost','127.0.0.1','::1'):raise ValueError('Use your local MySQL server: localhost or 127.0.0.1.')
    name='planflow_app_october_2026'
    base=dict(host=host,port=port,user=user,password=password)
    raw=pymysql.connect(**base,charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor,autocommit=True,connect_timeout=5)
    try:
        c=raw.cursor();c.execute('CREATE DATABASE IF NOT EXISTS `'+name+'` CHARACTER SET utf8mb4');c.execute('USE `'+name+'`')
        c.execute('SHOW TABLES');existing={next(iter(x.values())) for x in c.fetchall()}
        expected={'departments','shifts','daily_plans','plan_extras','scenarios','audit_log'}
        if existing and existing!=expected:raise ValueError('The project database has unexpected tables. No data was overwritten.')
        con=Connection(raw,True)
        if not existing:
            for statement in mysql_schema().split(';'):
                if statement.strip():c.execute(statement)
            raw.begin();seed(con);raw.commit()
        else:
            c.execute('SELECT version FROM daily_plans LIMIT 1');c.execute('SELECT paid_hours FROM plan_extras LIMIT 1')
            raw.begin();extend_sample_data(con);seed_scenarios(con);raw.commit()
        # Credentials stay in process memory. They are not stored or included in exports.
        with STATE_LOCK:MYSQL_CONFIG={**base,'database':name}
    except Exception:raw.rollback();raise
    finally:raw.close()
    return name

PLAN_SELECT='''SELECT p.*, e.scheduled_staff,e.absent_staff,e.paid_hours,e.overtime_hours,e.hourly_cost,e.overtime_rate,
e.dispatch_deadline,e.actual_cases,e.actual_staff,e.actual_productive_hours,e.actual_finished_at,
d.department_name,s.shift_name,s.start_time,s.end_time
FROM daily_plans p JOIN plan_extras e ON e.plan_id=p.plan_id
JOIN departments d ON d.department_id=p.department_id JOIN shifts s ON s.shift_id=p.shift_id'''

def fetch_plans(start,end,shift=0):
    sql=PLAN_SELECT+' WHERE p.plan_date>=? AND p.plan_date<=?'
    args=[start,end]
    if shift:sql+=' AND p.shift_id=?';args.append(shift)
    with connect() as con:return con.rows(sql+' ORDER BY p.plan_date,p.shift_id,p.department_id',args)

def metadata():
    with connect() as con:
        return {'departments':con.rows('SELECT * FROM departments'),'shifts':con.rows('SELECT * FROM shifts'),
                'backend':'MySQL' if con.mysql else 'SQLite demo','database':'planflow_app_october_2026' if con.mysql else 'Local demo',
                'month':'2026-10','start_date':'2026-10-01','end_date':'2026-12-31','sample_data':True}
