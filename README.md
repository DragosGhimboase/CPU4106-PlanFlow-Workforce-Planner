# PlanFlow

A working local Daily Workload and Staffing Planner for the group computing project. Uses HTML, CSS, JavaScript, Python, Flask, MySQL (when connected) and locally bundled Chart.js. A SQLite demo allows it to run before MySQL login. All operational records are fictional.

## Start on this laptop

1. Open this folder in File Explorer.
2. Double-click **Start_PlanFlow.cmd**. Keep its terminal open.
3. Open http://127.0.0.1:8765 if the browser does not open automatically.
4. Go to **Database connection** to connect MySQL. Enter your existing local host, port, username and password there, not in chat.
5. Click **Connect and prepare data**. The app creates only **planflow_app_october_2026** and uses that dedicated schema. Other databases are not modified. The existing schema name is retained for compatibility even though it now covers October–December.

The connection page accepts local MySQL only. Credentials stay in process memory and must be re-entered after restarting. Your demo database and MySQL database are independent: switching does not transfer edits between them. Use an account authorised to create a project schema and tables. Existing compatible project tables are retained; incompatible schemas are rejected rather than overwritten.

Python 3.11 or newer is needed on other laptops. The launcher creates a virtual environment and installs requirements on first use; internet is required for that installation. On this laptop the dependencies are already installed. After setup, the UI and charts run offline. This is a local workstation prototype, not a publicly hosted multi-user production service. Stop it with Ctrl+C in the terminal. Do not run two copies on port 8765.

If a server is already running, simply open its URL instead of starting another. If a browser reports connection refused, check the launcher terminal for errors. If the port is occupied by something else, start manually with a different PLANFLOW_PORT.

## Five project pages

- **Overview:** forecast, available staff, required staff, departmental shortages, capacity chart, cost and deadline warnings.
- **Workload:** add or edit forecasts, productivity, hours, headcounts, rates and deadline. A date/shift/department combination is unique.
- **Staffing:** change scheduled and absent headcounts; enter simulated actual performance. Updates persist and appear in the audit trail.
- **Scenarios:** change available staff and per-person overtime, compare cost/capacity/deadline risk, cover forecast automatically, save and reopen snapshots. Scenarios do not apply themselves to the current plan.
- **Reports:** filter dates and shifts, review forecast/capacity/actual charts, paginate records and export CSV.
- **Database connection:** choose MySQL or the existing local demo and review recent changes.

Dates start at 8 October 2026 to match the earlier mockup. The reference Day shift has 12,000 forecast cases, 17 available staff, 20 required, 10,200 capacity, and a 1,800-case shortfall. Three more staff cover volume, but the 13:30 deadline can still be at risk. Volume coverage and dispatch readiness are separate checks.

## Extended monthly data

92 dates × 2 shifts × 3 departments = **552 plans**, plus **552 extended records** and **36 full-shift saved scenario examples**. The period is 1 October–31 December 2026. Existing October records and edits are preserved; missing November and December keys are added automatically at demo startup or MySQL connection. Existing November/December plans are also retained.

Extra fields include scheduled/absent staff, paid hours, overtime, hourly and overtime rates, dispatch deadlines, actual cases, actual staff, actual productive hours and actual finish time. Sample actuals exist for the entire month, including future dates, and are explicitly labelled simulated. Newly added plans have no actuals until entered.

`database/planflow_october_to_december_2026.sql` is the complete schema and seeded sample for a new MySQL project database. Open it in Workbench and execute once if importing manually. It contains no DROP statements. Avoid importing over an existing populated project database. The app's connection screen can prepare it automatically instead.

The original older monthly SQL uses a different database name and schema. Do not use it as a substitute for this extended schema.

## Calculation assumptions

- Available staff = scheduled staff minus absences.
- Per-person capacity = productivity × (productive hours + overtime hours).
- Required staff = ceiling(forecast / per-person capacity).
- Case shortfall = max(forecast − available staff × per-person capacity, 0).
- Shortages are assessed within each department; spare capacity elsewhere is not assumed transferable.
- Illustrative planned cost = available staff × (paid shift hours × hourly cost + overtime hours × overtime rate). It is a prototype assumption, not payroll accounting; absent staff costs are excluded.
- Finish estimates spread productive work uniformly over paid shift hours. They do not model delivery routes, breaks at specific times, variable arrival times, queues or constraints between processing stages. Deadlines are same-day local times; predicted finishes may cross midnight and display the later date.
- Saved scenarios store baseline and proposed snapshots. Later edits to current plans do not change them.

## Project structure

`app.py`: Flask pages and validated API routes.
`db.py`: database schemas, seeding, MySQL configuration and SQLite adapter.
`data.py`: reproducible fictional month.
`logic.py`: independent Decimal-based calculations.
`templates/index.html`: page shell and accessible editing dialog.
`static/app.css` and `static/app.js`: interface and interactions.
`static/vendor/chart.umd.min.js`: Chart.js 4.5.0, locally bundled.
`test_app.py`: automated regression checks using temporary databases.
`.local/`: generated demo database and session key; excluded from Git and source ZIP.

## Verify and develop

Open this folder in VS Code. From its terminal:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_app
.\.venv\Scripts\python.exe app.py
```

19 automated checks cover data completeness, calculations, shortage isolation, absence edits, stale record protection, invalid inputs, duplicate plans, scenario isolation and snapshots, overtime costs, actuals, exports, page assets, CSRF and database constraints. Actual MySQL integration must also be checked after your authorised login. Tests do not access your live project database.

Use parameterised database queries in future changes. Mutation requests need the session CSRF token. The server binds to loopback; it is intended for the single local user. The project does not include individual employee records or planner user accounts.

## Team and assignment evidence

Ajiton Estibeiro: Scrum coordination, UX research and Penpot design.
Newton Lobo: front end.
Ioan-Dragos Ghimboase: Python calculations and back end.
Marcos Pereira: requirements prioritisation, MySQL, reports and testing.

Use `docs/UX_RESEARCH_AND_TESTING.md` to collect genuine research and usability results. It contains blank forms, not fabricated findings. Use Trello, stand-up notes, your actual GitHub contributions and test evidence to document your own learning. Each member should understand and adapt the implementation they present.

## References and library attribution

- Flask documentation: https://flask.palletsprojects.com/en/stable/
- MySQL constraints: https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html
- PyMySQL: https://pymysql.readthedocs.io/en/latest/
- Chart.js: https://www.chartjs.org/docs/latest/ (MIT; see static/vendor/Chartjs-LICENSE.txt)
- UN SDG 8: https://sdgs.un.org/goals/goal8
