"""Run: python -m unittest -v test_app. No real MySQL credentials required."""
import unittest, tempfile, json, csv, io
from pathlib import Path
import db
from app import app
from logic import calculate, summary

class PlanFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.previous_path=db.SQLITE_PATH;self.previous_config=db.MYSQL_CONFIG
        db.SQLITE_PATH=Path(self.temp.name)/'test.sqlite3';db.MYSQL_CONFIG=None
        db.init_demo();app.config['TESTING']=True
        self.client=app.test_client();self.client.get('/')
        with self.client.session_transaction() as s:self.headers={'X-CSRF-Token':s['csrf']}
    def tearDown(self):
        db.SQLITE_PATH=self.previous_path;db.MYSQL_CONFIG=self.previous_config;self.temp.cleanup()
    def get(self,path):
        res=self.client.get(path);self.assertEqual(res.status_code,200,res.data);return res.json
    def day(self):return self.get('/api/plans?date=2026-10-08&shift=1')
    def put(self,row):return self.client.put('/api/plans/'+str(row['plan_id']),json=row,headers=self.headers)
    def scenario(self):
        rows=self.day()['rows']
        return {'plan_date':'2026-10-08','shift_id':1,'changes':[{'plan_id':r['plan_id'],'proposed_staff':r['required_staff'],'overtime_hours':0} for r in rows]}

    def test_all_month_records_and_extras(self):
        r=self.get('/api/reports?start=2026-10-01&end=2026-10-31')
        self.assertEqual(len(r['rows']),186);self.assertEqual(len(r['days']),31)
        self.assertEqual(r['summary']['actual_records'],186)
        self.assertTrue(all(x['available_staff']==x['scheduled_staff']-x['absent_staff'] for x in r['rows']))
    def test_reference_dashboard(self):
        s=self.day()['summary']
        self.assertEqual([s[k] for k in ['forecast_cases','available_staff','required_staff','capacity_cases','staff_shortage','shortfall_cases']],[12000,17,20,10200,3,1800])

    def test_complete_quarter_and_month_boundaries(self):
        full=self.get('/api/reports?start=2026-10-01&end=2026-12-31')
        self.assertEqual(len(full['rows']),552);self.assertEqual(len(full['days']),92)
        for start,end,count in [('2026-11-01','2026-11-30',180),('2026-12-01','2026-12-31',186)]:
            result=self.get('/api/reports?start='+start+'&end='+end)
            self.assertEqual(len(result['rows']),count)
            self.assertTrue(all(x['available_staff']==x['scheduled_staff']-x['absent_staff'] for x in result['rows']))
        self.assertEqual(len(self.get('/api/plans?date=2026-12-31&shift=2')['rows']),3)
        self.assertEqual(self.get('/api/meta')['end_date'],'2026-12-31')

    def test_extension_preserves_existing_records_and_uses_real_ids(self):
        with db.connect() as con:
            con.execute("DELETE FROM plan_extras WHERE plan_id IN (SELECT plan_id FROM daily_plans WHERE plan_date>='2026-11-01')")
            con.execute("DELETE FROM daily_plans WHERE plan_date>='2026-11-01'")
            con.execute("UPDATE daily_plans SET notes='Retain my October edit',version=5 WHERE plan_id=1")
            con.execute("INSERT INTO daily_plans (plan_date,department_id,shift_id,forecast_cases,available_staff,cases_per_person_hour,productive_hours,notes,version) VALUES ('2027-01-01',1,1,100,1,100,6,'Custom record',1)")
            custom=con.one("SELECT plan_id FROM daily_plans WHERE plan_date='2027-01-01'")['plan_id']
            self.assertEqual(db.extend_sample_data(con),366)
            before=con.rows('SELECT * FROM daily_plans ORDER BY plan_id')
            self.assertEqual(db.extend_sample_data(con),0)
            self.assertEqual(before,con.rows('SELECT * FROM daily_plans ORDER BY plan_id'))
            self.assertEqual(con.one('SELECT notes,version FROM daily_plans WHERE plan_id=1'),{'notes':'Retain my October edit','version':5})
            self.assertEqual(con.one('SELECT notes FROM daily_plans WHERE plan_id=?',(custom,))['notes'],'Custom record')
            linked=con.rows(db.PLAN_SELECT+" WHERE p.plan_date>='2026-11-01' AND p.plan_date<='2026-12-31'")
            self.assertEqual(len(linked),366)
            self.assertTrue(all(x['dispatch_deadline'].startswith(x['plan_date']) for x in linked))
            row=linked[0];con.execute('UPDATE daily_plans SET notes=? WHERE plan_id=?',('Preserve November edit',row['plan_id']))
            self.assertEqual(db.extend_sample_data(con),0)
            self.assertEqual(con.one('SELECT notes FROM daily_plans WHERE plan_id=?',(row['plan_id'],))['notes'],'Preserve November edit')
    def test_rounding_and_zero_staff(self):
        row=self.day()['rows'][0];row.update(forecast_cases=1001,cases_per_person_hour=100,productive_hours=1)
        self.assertEqual(calculate(row)['required_staff'],11)
        zero=calculate(row,0);self.assertIsNone(zero['estimated_finish']);self.assertTrue(zero['deadline_risk'])
        row['forecast_cases']=0;zero=calculate(row,0);self.assertEqual(zero['required_staff'],0);self.assertFalse(zero['deadline_risk'])
    def test_department_shortfalls_not_net_offset(self):
        items=self.day()['rows'];items[0]=calculate(items[0],20);items[0]['available_staff']=20
        s=summary(items);self.assertGreater(s['capacity_cases'],s['forecast_cases']);self.assertEqual(s['staff_shortage'],1);self.assertEqual(s['shortfall_cases'],600)
    def test_absence_edit_persists_and_audits(self):
        row=self.day()['rows'][0];row.update(scheduled_staff=12,absent_staff=1)
        res=self.put(row);self.assertEqual(res.status_code,200,res.data)
        self.assertEqual(res.json['row']['available_staff'],11)
        self.assertEqual(self.day()['rows'][0]['available_staff'],11)
        self.assertEqual(self.get('/api/audit')['rows'][0]['action'],'update_plan')
    def test_stale_version_rejected(self):
        row=self.day()['rows'][0]
        self.assertEqual(self.put(row).status_code,200);self.assertEqual(self.put(row).status_code,409)
    def test_invalid_inputs_do_not_update(self):
        base=self.day()['rows'][0]
        for key,value in [('productive_hours',0),('absent_staff',10000),('scheduled_staff',-1),('forecast_cases',2.5),('cases_per_person_hour','NaN'),('productive_hours',9)]:
            with self.subTest(key=key,value=value):
                row=dict(base);row[key]=value;self.assertEqual(self.put(row).status_code,400)
        self.assertEqual(self.day()['rows'][0]['version'],base['version'])
    def test_create_and_duplicate(self):
        row=self.day()['rows'][0];row.update(plan_date='2027-01-01',dispatch_deadline='2027-01-01T13:30')
        r=self.client.post('/api/plans',json=row,headers=self.headers);self.assertEqual(r.status_code,201,r.data)
        self.assertIsNone(r.json['row']['actual_cases'])
        self.assertEqual(self.client.post('/api/plans',json=row,headers=self.headers).status_code,400)
    def test_scenario_covers_without_changing_baseline(self):
        before=self.day();r=self.client.post('/api/scenarios/compare',json=self.scenario(),headers=self.headers)
        self.assertEqual(r.status_code,200,r.data);self.assertEqual(r.json['proposed_summary']['shortfall_cases'],0)
        self.assertEqual(r.json['proposed_summary']['available_staff'],20)
        self.assertEqual(self.day(),before)
    def test_scenario_snapshot_survives_plan_changes(self):
        data=self.scenario();data['scenario_name']='Snapshot test'
        res=self.client.post('/api/scenarios',json=data,headers=self.headers);self.assertEqual(res.status_code,201,res.data)
        sid=res.json['scenario_id'];before=self.get('/api/scenarios/'+str(sid))
        row=self.day()['rows'][0];row['forecast_cases']=9999;self.assertEqual(self.put(row).status_code,200)
        after=self.get('/api/scenarios/'+str(sid));self.assertEqual(before,after)
    def test_scenario_overtime_cost_and_invalid_changes(self):
        d=self.scenario();d['changes'][0]['overtime_hours']=1
        result=self.client.post('/api/scenarios/compare',json=d,headers=self.headers).json
        self.assertEqual(result['proposed'][0]['capacity_cases'],7000)
        self.assertEqual(result['proposed'][0]['labour_cost'],10*(8*14.5+21.75))
        d['changes'][0]['plan_id']=9999
        self.assertEqual(self.client.post('/api/scenarios/compare',json=d,headers=self.headers).status_code,400)
    def test_actuals_updates_and_validation(self):
        row=self.day()['rows'][0]
        d={'version':row['version'],'actual_cases':5900,'actual_staff':10,'actual_productive_hours':6,'actual_finished_at':'2026-10-08T13:15'}
        res=self.client.put('/api/plans/'+str(row['plan_id'])+'/actuals',json=d,headers=self.headers)
        self.assertEqual(res.status_code,200,res.data);self.assertEqual(res.json['row']['actual_variance'],-100)
        self.assertFalse(res.json['row']['actual_late'])
        d['actual_finished_at']='2026-10-09T13:15'
        self.assertEqual(self.client.put('/api/plans/'+str(row['plan_id'])+'/actuals',json=d,headers=self.headers).status_code,400)
    def test_csv_and_report_totals(self):
        res=self.client.get('/api/reports.csv?start=2026-10-01&end=2026-10-31&shift=1')
        self.assertEqual(res.status_code,200)
        records=list(csv.DictReader(io.StringIO(res.data.decode('utf-8-sig'))));self.assertEqual(len(records),93)
        report=self.get('/api/reports?start=2026-10-01&end=2026-10-31&shift=1')
        self.assertEqual(sum(int(x['forecast_cases']) for x in records),report['summary']['forecast_cases'])
    def test_csrf_and_bad_dates(self):
        self.assertEqual(self.client.post('/api/scenarios/compare',json=self.scenario()).status_code,403)
        self.assertEqual(self.client.get('/api/plans?date=not-a-date').status_code,400)
        self.assertEqual(self.client.get('/api/reports?start=2026-10-31&end=2026-10-01').status_code,400)
    def test_all_pages_and_local_assets(self):
        for path in ['/overview','/workload','/staffing','/scenarios','/reports','/settings','/static/app.js','/static/app.css','/static/vendor/chart.umd.min.js']:
            res=self.client.get(path);self.assertEqual(res.status_code,200,path);res.close()
        self.assertEqual(self.client.get('/unknown').status_code,404)
    def test_seeded_scenario_examples(self):
        examples=self.get('/api/scenarios?date=2026-10-08&shift=1')['rows']
        self.assertEqual(len(examples),2)
        with db.connect() as c:self.assertEqual(c.one('SELECT COUNT(*) AS n FROM scenarios')['n'],36)
    def test_database_constraints(self):
        with db.connect() as c:
            for sql in ['UPDATE plan_extras SET absent_staff=scheduled_staff+1 WHERE plan_id=1','UPDATE daily_plans SET department_id=999 WHERE plan_id=1']:
                with self.assertRaises(Exception):c.execute(sql)

if __name__=='__main__':unittest.main()
