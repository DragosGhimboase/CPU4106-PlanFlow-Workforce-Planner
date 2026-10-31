"""PlanFlow local workstation application. Bind to loopback, not public networks."""
import os, secrets, json, csv, io, math
from decimal import Decimal
from datetime import date, datetime
from flask import Flask, request, jsonify, render_template, session, Response
import db
from logic import calculate, summary

db.init_demo()
app=Flask(__name__)
key=db.LOCAL/'session.key'
if not key.exists():key.write_bytes(secrets.token_bytes(32))
app.secret_key=key.read_bytes()
app.config.update(MAX_CONTENT_LENGTH=200_000,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict')

def jsonable(value):
    if isinstance(value,Decimal):return float(value)
    if isinstance(value,(date,datetime)):return value.isoformat()
    raise TypeError()

def dumps(value):return json.dumps(value,default=jsonable,ensure_ascii=False)
def reply(value,status=200):return Response(dumps(value),status=status,mimetype='application/json')

@app.before_request
def protect():
    host=request.host.split(':')[0]
    if host not in ('localhost','127.0.0.1','[','testserver'):return reply({'error':'This application is available only on localhost.'},403)
    if 'csrf' not in session:session['csrf']=secrets.token_urlsafe(24)
    if request.method in ('POST','PUT','DELETE'):
        if not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),session['csrf']):return reply({'error':'Reload the page and try again.'},403)

@app.after_request
def response_headers(response):
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Cache-Control']='no-store' if request.path.startswith('/api') else 'no-cache'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response

@app.errorhandler(ValueError)
def invalid(error):return reply({'error':str(error)},400)

@app.errorhandler(413)
def large(error):return reply({'error':'The request is too large.'},413)

def body():
    value=request.get_json(silent=True)
    if not isinstance(value,dict):raise ValueError('Send a valid JSON object.')
    return value

def number(data,key,minimum=0,maximum=1_000_000,integer=False):
    v=data.get(key)
    if isinstance(v,bool) or v in (None,''):raise ValueError(key.replace('_',' ')+' is required.')
    try:n=float(v)
    except (TypeError,ValueError):raise ValueError(key.replace('_',' ')+' must be numeric.')
    if not math.isfinite(n) or not minimum<=n<=maximum or (integer and not n.is_integer()):
        raise ValueError(key.replace('_',' ')+f' must be '+('a whole number ' if integer else '')+f'between {minimum} and {maximum}.')
    if not integer and round(n,2)!=n:raise ValueError(key.replace('_',' ')+' supports up to two decimal places.')
    return int(n) if integer else n

def valid_date(value):
    try:return date.fromisoformat(str(value)).isoformat()
    except (ValueError,TypeError):raise ValueError('Choose a valid date.')

def date_range():
    start=valid_date(request.args.get('start',request.args.get('date','2026-10-08')))
    end=valid_date(request.args.get('end',start))
    if start>end:raise ValueError('Start date must be before end date.')
    if (date.fromisoformat(end)-date.fromisoformat(start)).days>366:raise ValueError('Choose a range of up to 366 days.')
    shift=int(request.args.get('shift','0'))
    if shift not in (0,1,2):raise ValueError('Choose a valid shift.')
    return start,end,shift

@app.get('/')
@app.get('/<page>')
def index(page='overview'):
    if page not in ('overview','workload','staffing','scenarios','reports','settings'):return 'Page not found',404
    return render_template('index.html',page=page,csrf=session['csrf'])

@app.get('/api/meta')
def meta():return reply(db.metadata())

@app.get('/api/plans')
def plans():
    rows=[calculate(x) for x in db.fetch_plans(*date_range())]
    return reply({'rows':rows,'summary':summary(rows)})

def audit(con,action,entity,before,after):
    con.execute('INSERT INTO audit_log (changed_at,action,entity_id,before_json,after_json) VALUES (?,?,?,?,?)',
        (datetime.now().isoformat(timespec='seconds'),action,entity,dumps(before),dumps(after)))

@app.route('/api/plans',methods=['POST'])
@app.route('/api/plans/<int:plan_id>',methods=['PUT'])
def save_plan(plan_id=None):
    data=body();dt=valid_date(data.get('plan_date'))
    dep=number(data,'department_id',1,3,True);shift=number(data,'shift_id',1,2,True)
    forecast=number(data,'forecast_cases',0,1_000_000,True)
    rate=number(data,'cases_per_person_hour',.01,10000)
    hours=number(data,'productive_hours',.01,12)
    scheduled=number(data,'scheduled_staff',0,10000,True);absent=number(data,'absent_staff',0,scheduled,True)
    paid=number(data,'paid_hours',.01,12)
    if hours>paid:raise ValueError('Productive hours must not exceed paid shift hours.')
    overtime=number(data,'overtime_hours',0,4)
    wage=number(data,'hourly_cost',0,1000);ot_rate=number(data,'overtime_rate',0,2000)
    notes=str(data.get('notes','')).strip()
    if len(notes)>200:raise ValueError('Keep notes within 200 characters.')
    try:deadline=datetime.fromisoformat(str(data['dispatch_deadline']))
    except (KeyError,ValueError):raise ValueError('Choose a valid dispatch deadline.')
    if deadline.tzinfo or deadline.date().isoformat()!=dt:raise ValueError('The deadline must be on the plan date, in local time.')
    shift_start=datetime.fromisoformat(dt+('T06:00' if shift==1 else 'T14:00'))
    if deadline<=shift_start:raise ValueError('The deadline must be after the shift starts.')
    with db.connect() as con:
        before=con.one(db.PLAN_SELECT+' WHERE p.plan_id=?',(plan_id,)) if plan_id else None
        if plan_id and not before:return reply({'error':'Plan not found.'},404)
        duplicate=con.one('SELECT plan_id FROM daily_plans WHERE plan_date=? AND department_id=? AND shift_id=?',(dt,dep,shift))
        if duplicate and duplicate['plan_id']!=plan_id:raise ValueError('A plan already exists for this date, department and shift. Edit that plan instead.')
        vals=(dt,dep,shift,forecast,scheduled-absent,rate,hours,notes)
        if plan_id:
            version=number(data,'version',1,1_000_000,True)
            if version!=before['version']:return reply({'error':'This record changed. Reload and edit the latest version.'},409)
            cur=con.execute('UPDATE daily_plans SET plan_date=?,department_id=?,shift_id=?,forecast_cases=?,available_staff=?,cases_per_person_hour=?,productive_hours=?,notes=?,version=version+1 WHERE plan_id=? AND version=?',vals+(plan_id,version))
            if cur.rowcount!=1:return reply({'error':'This record changed. Reload and try again.'},409)
        else:
            cur=con.execute('INSERT INTO daily_plans (plan_date,department_id,shift_id,forecast_cases,available_staff,cases_per_person_hour,productive_hours,notes) VALUES (?,?,?,?,?,?,?,?)',vals);plan_id=cur.lastrowid
        extra=(scheduled,absent,paid,overtime,wage,ot_rate,deadline.isoformat(timespec='minutes'))
        if before:
            con.execute('UPDATE plan_extras SET scheduled_staff=?,absent_staff=?,paid_hours=?,overtime_hours=?,hourly_cost=?,overtime_rate=?,dispatch_deadline=? WHERE plan_id=?',extra+(plan_id,))
        else:
            con.execute('INSERT INTO plan_extras (scheduled_staff,absent_staff,paid_hours,overtime_hours,hourly_cost,overtime_rate,dispatch_deadline,plan_id) VALUES (?,?,?,?,?,?,?,?)',extra+(plan_id,))
        after=con.one(db.PLAN_SELECT+' WHERE p.plan_id=?',(plan_id,));audit(con,'update_plan' if before else 'create_plan',plan_id,before,after)
    return reply({'row':calculate(after)},200 if before else 201)

@app.put('/api/plans/<int:plan_id>/actuals')
def actuals(plan_id):
    data=body()
    cases=number(data,'actual_cases',0,1_000_000,True)
    staff=number(data,'actual_staff',0,10000,True)
    hours=number(data,'actual_productive_hours',.01,12)
    try:finish=datetime.fromisoformat(str(data['actual_finished_at']))
    except (KeyError,ValueError):raise ValueError('Enter a valid actual finish time.')
    if finish.tzinfo:raise ValueError('Use local time without a timezone suffix.')
    with db.connect() as con:
        before=con.one(db.PLAN_SELECT+' WHERE p.plan_id=?',(plan_id,))
        if not before:return reply({'error':'Plan not found.'},404)
        if finish.date().isoformat()!=before['plan_date']:raise ValueError('Actual finish must be on the plan date.')
        start=datetime.fromisoformat(before['plan_date']+'T'+before['start_time'])
        if finish<start:raise ValueError('Actual finish must not be before the shift starts.')
        version=number(data,'version',1,1_000_000,True)
        cur=con.execute('UPDATE daily_plans SET version=version+1 WHERE plan_id=? AND version=?',(plan_id,version))
        if cur.rowcount!=1:return reply({'error':'This record changed. Reload and try again.'},409)
        con.execute('UPDATE plan_extras SET actual_cases=?,actual_staff=?,actual_productive_hours=?,actual_finished_at=? WHERE plan_id=?',(cases,staff,hours,finish.isoformat(timespec='minutes'),plan_id))
        after=con.one(db.PLAN_SELECT+' WHERE p.plan_id=?',(plan_id,));audit(con,'update_actuals',plan_id,before,after)
    return reply({'row':calculate(after)})

def comparison(data):
    dt=valid_date(data.get('plan_date'));shift=number(data,'shift_id',1,2,True)
    base=[calculate(x) for x in db.fetch_plans(dt,dt,shift)]
    if not base:raise ValueError('No plans exist for the selected date and shift.')
    changes=data.get('changes')
    if not isinstance(changes,list) or len(changes)!=len(base):raise ValueError('Supply one scenario change for each department.')
    by_id={}
    for change in changes:
        if not isinstance(change,dict):raise ValueError('Invalid scenario change.')
        pid=number(change,'plan_id',1,1000000,True)
        if pid in by_id:raise ValueError('Each department must appear once.')
        by_id[pid]=change
    if set(by_id)!=set(x['plan_id'] for x in base):raise ValueError('Scenario records do not match the selected plans.')
    proposed=[]
    for row in base:
        change=by_id[row['plan_id']]
        staff=number(change,'proposed_staff',0,10000,True)
        ot=number(change,'overtime_hours',0,4)
        result=calculate(row,staff,ot)
        result['available_staff']=staff;result['overtime_hours']=ot
        proposed.append(result)
    return {'base':base,'proposed':proposed,'base_summary':summary(base),'proposed_summary':summary(proposed)}

@app.post('/api/scenarios/compare')
def compare():return reply(comparison(body()))

@app.post('/api/scenarios')
def save_scenario():
    data=body();name=str(data.get('scenario_name','')).strip()
    if not name or len(name)>100:raise ValueError('Use a scenario name between 1 and 100 characters.')
    result=comparison(data)
    with db.connect() as con:
        cur=con.execute('INSERT INTO scenarios (scenario_name,plan_date,shift_id,created_at,base_json,proposed_json,result_json) VALUES (?,?,?,?,?,?,?)',
            (name,data['plan_date'],data['shift_id'],datetime.now().isoformat(timespec='seconds'),dumps(result['base']),dumps(result['proposed']),dumps({'base_summary':result['base_summary'],'proposed_summary':result['proposed_summary']})))
        sid=cur.lastrowid;audit(con,'save_scenario',sid,None,{'name':name})
    return reply({'scenario_id':sid,'message':'Scenario saved as an independent snapshot.'},201)

@app.get('/api/scenarios')
def list_scenarios():
    dt=valid_date(request.args.get('date','2026-10-08'));shift=int(request.args.get('shift','1'))
    with db.connect() as con:rows=con.rows('SELECT scenario_id,scenario_name,created_at FROM scenarios WHERE plan_date=? AND shift_id=? ORDER BY scenario_id DESC',(dt,shift))
    return reply({'rows':rows})

@app.get('/api/scenarios/<int:sid>')
def get_scenario(sid):
    with db.connect() as con:row=con.one('SELECT * FROM scenarios WHERE scenario_id=?',(sid,))
    if not row:return reply({'error':'Scenario not found.'},404)
    result=json.loads(row['result_json']);result.update(base=json.loads(row['base_json']),proposed=json.loads(row['proposed_json']),scenario_name=row['scenario_name'],saved=True)
    return reply(result)

@app.get('/api/reports')
def report():
    rows=[calculate(x) for x in db.fetch_plans(*date_range())]
    groups={}
    for row in rows:groups.setdefault(row['plan_date'],[]).append(row)
    days=[{'plan_date':dt,**summary(items)} for dt,items in groups.items()]
    totals=summary(rows);totals['coverage_pct']=round(totals['capacity_cases']/totals['forecast_cases']*100,1) if totals['forecast_cases'] else None
    totals['shortage_records']=sum(x['staff_shortage']>0 for x in rows)
    totals['late_actuals']=sum(x['actual_late'] is True for x in rows)
    return reply({'rows':rows,'days':days,'summary':totals})

@app.get('/api/reports.csv')
def export():
    rows=[calculate(x) for x in db.fetch_plans(*date_range())]
    cols=['plan_date','department_name','shift_name','forecast_cases','scheduled_staff','absent_staff','available_staff','required_staff','productive_hours','overtime_hours','capacity_cases','staff_shortage','shortfall_cases','labour_cost','dispatch_deadline','estimated_finish','deadline_risk','actual_cases','actual_staff','actual_productive_hours','actual_variance','actual_finished_at']
    buf=io.StringIO(newline='');writer=csv.writer(buf);writer.writerow(cols)
    for row in rows:writer.writerow([row.get(k,'') for k in cols])
    return Response('\ufeff'+buf.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="planflow_report.csv"'})

@app.get('/api/audit')
def logs():
    with db.connect() as con:rows=con.rows('SELECT audit_id,changed_at,action,entity_id FROM audit_log ORDER BY audit_id DESC LIMIT 20')
    return reply({'rows':rows})

@app.post('/api/database/mysql')
def mysql_setup():
    data=body();host=str(data.get('host','localhost'));port=number(data,'port',1,65535,True)
    user=str(data.get('user','')).strip();password=str(data.get('password',''))
    if not user or len(user)>100 or len(password)>200:raise ValueError('Enter a valid MySQL username and password.')
    try:name=db.configure_mysql(host,port,user,password)
    except ValueError:raise
    except Exception:return reply({'error':'MySQL connection failed. Check host, port, username, password and database creation permission. Your existing databases were not changed.'},400)
    return reply({'message':'Connected to '+name+'. Credentials remain in memory until the app stops.','backend':'MySQL'})

@app.post('/api/database/demo')
def use_demo():
    with db.STATE_LOCK:db.MYSQL_CONFIG=None
    return reply({'message':'Switched to the existing local demo database.'})

@app.get('/api/health')
def health():return reply({'status':'ok','backend':db.metadata()['backend']})

if __name__=='__main__':
    port=int(os.environ.get('PLANFLOW_PORT','8765'))
    print(f'PlanFlow: http://127.0.0.1:{port} (local laptop only)',flush=True)
    if os.environ.get('PLANFLOW_OPEN_BROWSER')=='1':
        import threading,webbrowser
        threading.Timer(1.5,lambda:webbrowser.open(f'http://127.0.0.1:{port}')).start()
    app.run(host='127.0.0.1',port=port,debug=False)
