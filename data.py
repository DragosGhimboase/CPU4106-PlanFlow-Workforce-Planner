"""Reproducible fictional October–December 2026 dataset; no real records."""
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_CEILING
import random

DEPARTMENTS=[(1,'Picking'),(2,'Packing'),(3,'Dispatch')]
SHIFTS=[(1,'Day shift','06:00:00','14:00:00'),(2,'Late shift','14:00:00','22:00:00')]
PLAN_COLUMNS=['plan_date','department_id','shift_id','forecast_cases','available_staff','cases_per_person_hour','productive_hours','notes','version']
EXTRA_COLUMNS=['plan_id','scheduled_staff','absent_staff','paid_hours','overtime_hours','hourly_cost','overtime_rate','dispatch_deadline','actual_cases','actual_staff','actual_productive_hours','actual_finished_at']

def sample_data():
    rng=random.Random(4106)
    plans=[];extras=[]
    for offset in range(92):
        dt=date(2026,10,1)+timedelta(days=offset)
        day=dt.day
        for shift in (1,2):
            for dep in (1,2,3):
                hours=Decimal('6') if shift==1 else Decimal('5.5')
                rate=Decimal({1:100,2:90,3:80}[dep])
                factor=Decimal('1.15') if dt.weekday() in (4,5) else Decimal('.85') if dt.weekday()==6 else Decimal(1)
                if shift==2:factor*=Decimal('.7')
                forecast=int(Decimal({1:6000,2:3600,3:2400}[dep])*factor*Decimal(str(rng.uniform(.9,1.1)))//50*50)
                required=int((Decimal(forecast)/(rate*hours)).to_integral_value(rounding=ROUND_CEILING))
                staff=max(0,required+rng.choice([-2,-1,0,0,1,2]))
                if dt==date(2026,10,8) and shift==1:
                    forecast={1:6000,2:3600,3:2400}[dep];staff={1:8,2:5,3:4}[dep];hours=Decimal(6);rate=Decimal(100)
                if dt==date(2026,10,10) and shift==1:forecast=int(staff*rate*hours)
                plan_id=len(plans)+1
                plans.append((dt.isoformat(),dep,shift,forecast,staff,float(rate),float(hours),'Fictional student project data',1))
                # Separate RNG ensures extended fields do not change base forecasts.
                extra_rng=random.Random(plan_id+9000)
                absent=extra_rng.choice([0,0,0,1,2])
                wage={1:14.5,2:14,3:15.5}[dep]
                deadline=datetime.combine(dt,datetime.strptime('13:30' if shift==1 else '21:30','%H:%M').time())
                ah=round(float(hours)*extra_rng.uniform(.9,1.03),2)
                actual=max(0,int(staff*float(rate)*ah*extra_rng.uniform(.88,1.05)//10*10))
                finish=deadline+timedelta(minutes=extra_rng.choice([-45,-25,-10,5,20,40]))
                extras.append((plan_id,staff+absent,absent,8,0,wage,round(wage*1.5,2),deadline.isoformat(timespec='minutes'),actual,staff,ah,finish.isoformat(timespec='minutes')))
    return plans,extras
