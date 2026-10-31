"""Pure planning calculations. Monetary amounts are illustrative GBP."""
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from datetime import datetime, timedelta

def dec(value):
    return Decimal(str(value))

def calculate(row, staff=None, overtime=None):
    staff = row['available_staff'] if staff is None else staff
    overtime = row['overtime_hours'] if overtime is None else overtime
    rate = dec(row['cases_per_person_hour'])
    hours = dec(row['productive_hours']) + dec(overtime)
    forecast = int(row['forecast_cases'])
    required = int((dec(forecast) / (rate * hours)).to_integral_value(rounding=ROUND_CEILING))
    capacity = dec(staff) * rate * hours
    cost = dec(staff) * (dec(row['paid_hours']) * dec(row['hourly_cost']) + dec(overtime) * dec(row['overtime_rate']))
    shortage = max(required - staff, 0)
    shortfall = max(dec(forecast) - capacity, Decimal(0))
    # Illustrative elapsed-time estimate: productive work distributed across paid shift.
    start = datetime.fromisoformat(str(row['plan_date']) + 'T' + str(row['start_time']))
    deadline = datetime.fromisoformat(str(row['dispatch_deadline']))
    elapsed = Decimal(0) if not forecast else (dec(forecast) / (dec(staff) * rate)) * dec(row['paid_hours']) / dec(row['productive_hours']) if staff else None
    completion = start + timedelta(hours=float(elapsed)) if elapsed is not None else None
    actual_cases = row.get('actual_cases')
    result = dict(row)
    result.update(required_staff=required, capacity_cases=float(capacity), staff_shortage=shortage,
        shortfall_cases=float(shortfall), capacity_balance=float(capacity - forecast),
        labour_cost=float(cost.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)),
        planning_status='Shortage' if shortfall else 'Balanced' if capacity == forecast else 'Spare capacity',
        estimated_finish=completion.isoformat(timespec='minutes') if completion else None,
        deadline_risk=completion is None or completion > deadline,
        actual_variance=None if actual_cases is None else int(actual_cases) - forecast,
        actual_late=None if not row.get('actual_finished_at') else datetime.fromisoformat(str(row['actual_finished_at'])) > deadline)
    return result

def summary(rows):
    return {
        'forecast_cases':sum(x['forecast_cases'] for x in rows),
        'available_staff':sum(x['available_staff'] for x in rows),
        'required_staff':sum(x['required_staff'] for x in rows),
        'capacity_cases':round(sum(x['capacity_cases'] for x in rows),2),
        'staff_shortage':sum(x['staff_shortage'] for x in rows),
        'shortfall_cases':round(sum(x['shortfall_cases'] for x in rows),2),
        'labour_cost':round(sum(x['labour_cost'] for x in rows),2),
        'deadline_risks':sum(bool(x['deadline_risk']) for x in rows),
        'actual_cases':sum(x['actual_cases'] or 0 for x in rows),
        'actual_records':sum(x['actual_cases'] is not None for x in rows)
    }
