'use strict';
const page=document.body.dataset.page;
const $=(id)=>document.getElementById(id);
const esc=(v)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v)=>Number(v??0).toLocaleString('en-GB',{maximumFractionDigits:1});
const money=(v)=>new Intl.NumberFormat('en-GB',{style:'currency',currency:'GBP',maximumFractionDigits:2}).format(v??0);
const time=(v)=>v?String(v).slice(11,16):'—';
const finishTime=(v,dt)=>v?(String(v).slice(0,10)===dt?time(v):`${String(v).slice(0,10)} ${time(v)}`):'No capacity';
const csrf=document.querySelector('meta[name="csrf-token"]').content;
let meta, rows=[], charts=[], editRow=null, editingActuals=false, loadSerial=0, reportsData=null, reportPage=0;
const titles={overview:['Daily planning overview','A clear view of workload, people and capacity.'],workload:['Workload planning','Set demand and the assumptions behind your plan.'],staffing:['Staffing allocation','Adjust availability and spot gaps before the shift starts.'],scenarios:['Scenario comparison','Explore staffing changes before committing to a plan.'],reports:['Planning reports','Review capacity, costs and simulated actual performance.'],settings:['Database connection','Connect your project to the MySQL server on this laptop.']};
$('title').textContent=titles[page][0];$('subtitle').textContent=titles[page][1];$('breadcrumb').textContent=page.charAt(0).toUpperCase()+page.slice(1);
document.querySelector(`[data-nav="${page}"]`)?.classList.add('active');
document.querySelector(`[data-nav="${page}"]`)?.setAttribute('aria-current','page');
try{$('filter-date').value=localStorage.getItem('planflow-date')||'2026-10-08';$('filter-shift').value=localStorage.getItem('planflow-shift')||'1';}catch{}
if(['settings','reports'].includes(page))$('filters').hidden=true;

async function api(path,method='GET',body){
  const res=await fetch(path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body?JSON.stringify(body):undefined});
  const text=await res.text();let value;
  try{value=JSON.parse(text);}catch{throw new Error('The server could not complete the request. Check the app terminal and try again.');}
  if(!res.ok)throw new Error(value.error||'The request failed.');return value;
}
function showError(error){$('error').textContent=error.message||String(error);$('error').hidden=false;}
function clearError(){$('error').hidden=true;}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,3500);}
function destroyCharts(){charts.forEach(c=>c.destroy());charts=[];}
function metrics(items){return `<div class="metrics">${items.map(([label,value,note,icon,warning])=>`<div class="metric ${warning?'warning':''}"><span class="metric-icon" aria-hidden="true">${icon}</span><div class="metric-label">${label}</div><div class="metric-number">${value}</div><div class="metric-note">${note}</div></div>`).join('')}</div>`;}
function badge(row){return `<span class="badge ${row.planning_status==='Shortage'?'error':row.planning_status==='Balanced'?'':'neutral'}">${esc(row.planning_status)}</span>`;}
function empty(text='No plans for this date and shift.'){return `<div class="panel empty"><h2>${text}</h2><p>Choose another date or add a workload plan.</p><a class="button" href="/workload">Open Workload</a></div>`;}
function chart(id,labels,datasets){
  const canvas=$(id);if(!canvas)return;
  if(typeof Chart==='undefined'){canvas.parentElement.textContent='Charts are unavailable. The table contains the same figures.';return;}
  charts.push(new Chart(canvas,{type:'bar',data:{labels,datasets},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{color:'#52647A',boxWidth:10,boxHeight:10,font:{family:'Segoe UI',size:11},padding:18}}},scales:{x:{grid:{display:false},ticks:{color:'#52647A',font:{size:11}}},y:{beginAtZero:true,grid:{color:'#E8EDF4'},ticks:{color:'#52647A',font:{size:10}}}},datasets:{bar:{borderRadius:4,maxBarThickness:38}}}}));
}
function panelHead(title,desc='',action=''){return `<div class="panel-head"><div><h2>${title}</h2>${desc?`<p class="small">${desc}</p>`:''}</div>${action}</div>`;}
function planTable(items,actions=true){return `<div class="table-scroll"><table><thead><tr><th>Department</th><th class="number">Forecast cases</th><th class="number">Available</th><th class="number">Required</th><th class="number">Capacity</th><th>Status</th>${actions?'<th>Action</th>':''}</tr></thead><tbody>${items.map(r=>`<tr><td><strong>${esc(r.department_name)}</strong></td><td class="number">${fmt(r.forecast_cases)}</td><td class="number">${fmt(r.available_staff)}</td><td class="number">${fmt(r.required_staff)}</td><td class="number">${fmt(r.capacity_cases)}</td><td>${badge(r)}</td>${actions?`<td><button class="link-button" data-edit="${r.plan_id}">Edit plan</button></td>`:''}</tr>`).join('')}</tbody></table></div>`;}

async function load(){
  clearError();destroyCharts();const serial=++loadSerial;
  if(page==='settings'){renderSettings();return;}
  if(page==='reports'){renderReportsShell();await loadReport();return;}
  const data=await api(`/api/plans?date=${$('filter-date').value}&shift=${$('filter-shift').value}`);
  if(serial!==loadSerial)return;rows=data.rows;
  if(page==='overview')renderOverview(data.summary);
  if(page==='workload')renderWorkload(data.summary);
  if(page==='staffing')renderStaffing(data.summary);
  if(page==='scenarios'){renderScenarios();if(rows.length){await compareScenario();await savedScenarios();}}
}
function renderOverview(s){
  if(!rows.length){$('content').innerHTML=empty();return;}
  $('content').innerHTML=metrics([['Forecast cases',fmt(s.forecast_cases),'Across three departments','▣'],['Available staff',fmt(s.available_staff),`${fmt(rows.reduce((n,r)=>n+r.absent_staff,0))} absences accounted for`,'♙'],['Required staff',fmt(s.required_staff),'Rounded up within each department','⇧'],['Staff shortage',fmt(s.staff_shortage),`${fmt(s.shortfall_cases)} cases beyond capacity`,'!',s.staff_shortage>0]])+
  `<div class="notice ${s.staff_shortage?'':'success'}">${s.staff_shortage?`<strong>Capacity shortfall: ${fmt(s.shortfall_cases)} cases.</strong> Review staffing by department before finalising your plan.`:'<strong>All departments have sufficient planned capacity.</strong> Review deadlines before finalising your plan.'}</div>`+
  `<div class="grid-two"><section class="panel">${panelHead('Workload vs capacity','Forecast cases compared with configured staffing capacity')}<div class="chart-box"><canvas id="overview-chart" aria-label="Workload and capacity by department" role="img"></canvas></div></section><section class="panel">${panelHead('Capacity by department','Spare capacity cannot automatically cover another department')}${rows.map(r=>`<div class="capacity-item"><div class="capacity-label"><strong>${esc(r.department_name)}</strong><small>${fmt(r.capacity_cases)} / ${fmt(r.forecast_cases)} cases</small></div><progress max="100" value="${r.forecast_cases?Math.min(100,100*r.capacity_cases/r.forecast_cases):100}" aria-label="${esc(r.department_name)} capacity coverage"></progress></div>`).join('')}<p class="help">Estimated labour cost <strong>${money(s.labour_cost)}</strong> · ${s.deadline_risks} deadline risks</p><a class="link-button" href="/scenarios">Compare a staffing scenario →</a></section></div>`+
  `<section class="panel">${panelHead('Staffing by department','All figures refer to the selected shift',`<a class="button secondary small" href="/staffing">Manage staffing</a>`)}${planTable(rows)}</section>`+
  `<section class="panel">${panelHead('Dispatch readiness','Finish estimates assume work is spread evenly through the paid shift')}<div class="table-scroll"><table><thead><tr><th>Department</th><th>Deadline</th><th>Estimated finish</th><th>Readiness</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.department_name)}</td><td>${time(r.dispatch_deadline)}</td><td>${finishTime(r.estimated_finish,r.plan_date)}</td><td><span class="badge ${r.deadline_risk?'warning':''}">${r.deadline_risk?'Deadline at risk':'Within deadline'}</span></td></tr>`).join('')}</tbody></table></div></section>`;
  chart('overview-chart',rows.map(r=>r.department_name),[{label:'Forecast cases',data:rows.map(r=>r.forecast_cases),backgroundColor:'#2563EB',borderColor:'#1D4ED8',borderWidth:1},{label:'Planned capacity',data:rows.map(r=>r.capacity_cases),backgroundColor:'#15803D',borderColor:'#166534',borderWidth:1}]);
}
function renderWorkload(s){
  $('content').innerHTML=metrics([['Forecast cases',fmt(s.forecast_cases),'Selected date and shift','▣'],['Departments',rows.length,'With a saved workload plan','▤'],['Productive hours',rows.length?fmt(rows[0].productive_hours):'—','Per person; varies by department','◷'],['Required staff',fmt(s.required_staff),'Forecast ÷ per-person capacity','♙']])+ 
  `<section class="panel">${panelHead('Workload by department','Configure demand, productivity and productive time',`<button class="button" id="add-plan">＋ Add workload</button>`)}${rows.length?`<div class="table-scroll"><table><thead><tr><th>Department</th><th class="number">Forecast cases</th><th class="number">Cases/person/hour</th><th class="number">Productive hours</th><th>Deadline</th><th>Action</th></tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${esc(r.department_name)}</strong></td><td class="number">${fmt(r.forecast_cases)}</td><td class="number">${fmt(r.cases_per_person_hour)}</td><td class="number">${fmt(r.productive_hours)}</td><td>${time(r.dispatch_deadline)}</td><td><button class="link-button" data-edit="${r.plan_id}">Edit workload</button></td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">Add your first department plan for this shift.</div>'}<p class="help">Required staff = forecast cases ÷ (cases per person per hour × productive hours), rounded up. Overtime adds productive capacity separately.</p></section>`+
  `<section class="panel">${panelHead('Workload distribution','Cases to process in each department')}<div class="chart-box"><canvas id="workload-chart" role="img" aria-label="Forecast cases by department"></canvas></div></section>`;
  chart('workload-chart',rows.map(r=>r.department_name),[{label:'Forecast cases',data:rows.map(r=>r.forecast_cases),backgroundColor:'#2563EB',borderColor:'#1D4ED8',borderWidth:1}]);
}
function renderStaffing(s){
  if(!rows.length){$('content').innerHTML=empty();return;}
  const absences=rows.reduce((n,r)=>n+r.absent_staff,0);
  $('content').innerHTML=metrics([['Scheduled staff',fmt(s.available_staff+absences),'Before absences','♙'],['Available staff',fmt(s.available_staff),'Scheduled minus absent','✓'],['Absences',fmt(absences),'Headcounts only; no personal data','−'],['Staff shortage',fmt(s.staff_shortage),'Departmental gaps total','!',s.staff_shortage>0]])+
  `<section class="panel">${panelHead('Staffing allocation','Update one department at a time; changes are saved to the database')}<div class="table-scroll"><table><thead><tr><th>Department</th><th>Scheduled</th><th>Absent</th><th class="number">Available</th><th class="number">Required</th><th>Status</th><th>Actions</th></tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${esc(r.department_name)}</strong></td><td><input class="inline-field" type="number" min="0" max="10000" step="1" id="scheduled-${r.plan_id}" value="${r.scheduled_staff}" aria-label="${esc(r.department_name)} scheduled staff"></td><td><input class="inline-field" type="number" min="0" max="10000" step="1" id="absent-${r.plan_id}" value="${r.absent_staff}" aria-label="${esc(r.department_name)} absent staff"></td><td class="number">${fmt(r.available_staff)}</td><td class="number">${fmt(r.required_staff)}</td><td>${badge(r)}</td><td><button class="button small" data-staff-save="${r.plan_id}">Save</button> <button class="button secondary small" data-edit="${r.plan_id}">Details</button></td></tr>`).join('')}</tbody></table></div><p class="help">Saved availability = scheduled staff − absent staff. Costs use available staff, paid hours and the configured overtime rate.</p></section>`+
  `<section class="panel">${panelHead('Simulated actual performance')}<div class="table-scroll"><table><thead><tr><th>Department</th><th class="number">Forecast</th><th class="number">Actual cases</th><th class="number">Variance</th><th>Actual finish</th><th>Action</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.department_name)}</td><td class="number">${fmt(r.forecast_cases)}</td><td class="number">${r.actual_cases===null?'—':fmt(r.actual_cases)}</td><td class="number ${r.actual_variance<0?'negative':'positive'}">${r.actual_variance===null?'—':fmt(r.actual_variance)}</td><td>${time(r.actual_finished_at)}</td><td><button class="link-button" data-actual="${r.plan_id}">Record actuals</button></td></tr>`).join('')}</tbody></table></div></section>`;
}
function renderScenarios(){
  if(!rows.length){$('content').innerHTML=empty();return;}
  $('content').innerHTML=`<div id="comparison"></div><section class="panel">${panelHead('Adjust staffing and overtime','Compare the whole shift while keeping each department separate')}<div class="table-scroll"><table><thead><tr><th>Department</th><th class="number">Current staff</th><th>Proposed staff</th><th>Overtime/person</th><th class="number">Required staff now</th></tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${esc(r.department_name)}</strong></td><td class="number">${r.available_staff}</td><td><input class="inline-field" type="number" min="0" max="10000" step="1" id="proposed-${r.plan_id}" value="${r.available_staff}" aria-label="${esc(r.department_name)} proposed staff"></td><td><input class="inline-field" type="number" min="0" max="4" step="0.25" id="overtime-${r.plan_id}" value="${r.overtime_hours}" aria-label="${esc(r.department_name)} overtime hours"> hours</td><td class="number">${r.required_staff}</td></tr>`).join('')}</tbody></table></div><p class="help">Regular costs use paid hours. Overtime is paid at the separate overtime rate. More capacity does not guarantee dispatch deadlines.</p><div class="button-row"><button class="button" id="calculate-scenario">Compare scenario</button><button class="button secondary" id="cover-forecast">Cover forecast</button></div></section><section class="panel">${panelHead('Save a scenario','Save an independent snapshot; the current plan stays unchanged')}<div class="button-row"><input class="scenario-name" id="scenario-name" maxlength="100" placeholder="e.g. Cover day-shift demand" aria-label="Scenario name"><button class="button" id="save-scenario">Save scenario</button></div><h3>Saved comparisons</h3><div class="saved-list" id="saved-scenarios"></div></section>`;
}
function scenarioPayload(){return {plan_date:$('filter-date').value,shift_id:Number($('filter-shift').value),changes:rows.map(r=>({plan_id:r.plan_id,proposed_staff:$(`proposed-${r.plan_id}`).value,overtime_hours:$(`overtime-${r.plan_id}`).value}))};}
function comparisonCard(title,s,proposed=false){return `<div class="comparison-card ${proposed?'proposed':''}"><h2>${title}</h2><div class="comparison-numbers"><div><strong>${fmt(s.available_staff)}</strong><span>Staff</span></div><div><strong>${fmt(s.capacity_cases)}</strong><span>Capacity cases</span></div><div><strong>${fmt(s.shortfall_cases)}</strong><span>Shortfall cases</span></div></div><div class="comparison-cost">Estimated cost <strong>${money(s.labour_cost)}</strong> · ${s.deadline_risks} deadline risks</div></div>`;}
async function compareScenario(){const result=await api('/api/scenarios/compare','POST',scenarioPayload());renderComparison(result);return result;}
function renderComparison(r){$('comparison').innerHTML=`${r.saved?`<div class="notice">Saved snapshot: <strong>${esc(r.scenario_name)}</strong>. Figures refer to the plan at the time of saving.</div>`:''}<div class="comparison">${comparisonCard(r.saved?'Original snapshot':'Current plan',r.base_summary)}${comparisonCard('Proposed plan',r.proposed_summary,true)}</div><div class="notice ${r.proposed_summary.staff_shortage?'':'success'}">${r.proposed_summary.staff_shortage?`${fmt(r.proposed_summary.staff_shortage)} staff still needed across departments.`:'The proposed plan covers forecast volume in all departments.'} Cost difference: <strong>${money(r.proposed_summary.labour_cost-r.base_summary.labour_cost)}</strong>.</div>`;}
async function savedScenarios(){const data=await api(`/api/scenarios?date=${$('filter-date').value}&shift=${$('filter-shift').value}`);$('saved-scenarios').innerHTML=data.rows.length?data.rows.map(r=>`<button class="button secondary small" data-scenario="${r.scenario_id}">${esc(r.scenario_name)}</button>`).join(''):'<p class="help">No saved scenarios yet. Compare an option and save it above.</p>';}

function renderReportsShell(){
  $('content').innerHTML=`<form class="report-filters" id="report-filter-form"><label>Start date<input type="date" id="report-start" value="2026-10-01" required></label><label>End date<input type="date" id="report-end" value="2026-12-31" required></label><label>Shift<select id="report-shift"><option value="0">All shifts</option><option value="1">Day shift</option><option value="2">Late shift</option></select></label><button class="button" type="submit">Update report</button><button class="button secondary" type="button" id="export-csv">Export CSV</button></form><div id="report-result"><div class="loading">Loading period report…</div></div>`;
}
function reportQuery(){return `start=${$('report-start').value}&end=${$('report-end').value}&shift=${$('report-shift').value}`;}
async function loadReport(){
  destroyCharts();reportsData=await api('/api/reports?'+reportQuery());reportPage=0;const s=reportsData.summary;
  $('report-result').innerHTML=metrics([['Forecast cases',fmt(s.forecast_cases),`${reportsData.rows.length} department-shift records`,'▣'],['Planned capacity',fmt(s.capacity_cases),s.coverage_pct===null?'No forecast':'Aggregate coverage '+fmt(s.coverage_pct)+'%','▥'],['Labour cost',money(s.labour_cost),'Illustrative planned GBP costs','£'],['Shortage records',fmt(s.shortage_records),'Department-shifts with staffing gaps','!',s.shortage_records>0]])+
  `<section class="panel">${panelHead('Daily workload and performance','Aggregate planned capacity and simulated actual cases')}<div class="chart-box wide"><canvas id="report-chart" role="img" aria-label="Daily forecast capacity and actual cases"></canvas></div></section><section class="panel">${panelHead('Detailed planning report',`${fmt(s.shortfall_cases)} unmet departmental cases · ${s.deadline_risks} estimated deadline risks · ${s.late_actuals} simulated late finishes`)}<div id="report-table"></div></section>`;
  chart('report-chart',reportsData.days.map(r=>r.plan_date.slice(8)),[{label:'Forecast',data:reportsData.days.map(r=>r.forecast_cases),backgroundColor:'#2563EB',borderColor:'#1D4ED8',borderWidth:1},{label:'Capacity',data:reportsData.days.map(r=>r.capacity_cases),backgroundColor:'#15803D',borderColor:'#166534',borderWidth:1},{label:'Simulated actual',data:reportsData.days.map(r=>r.actual_records?r.actual_cases:null),backgroundColor:'#B45309',borderColor:'#92400E',borderWidth:1}]);renderReportTable();
}
function renderReportTable(){
  const all=reportsData.rows;const items=all.slice(reportPage*12,reportPage*12+12);const max=Math.max(0,Math.ceil(all.length/12)-1);
  $('report-table').innerHTML=items.length?`<div class="table-scroll"><table><thead><tr><th>Date</th><th>Shift</th><th>Department</th><th class="number">Forecast</th><th class="number">Capacity</th><th class="number">Actual</th><th class="number">Cost</th><th>Status</th></tr></thead><tbody>${items.map(r=>`<tr><td>${esc(r.plan_date.slice(5))}</td><td>${esc(r.shift_name)}</td><td>${esc(r.department_name)}</td><td class="number">${fmt(r.forecast_cases)}</td><td class="number">${fmt(r.capacity_cases)}</td><td class="number">${r.actual_cases===null?'—':fmt(r.actual_cases)}</td><td class="number">${money(r.labour_cost)}</td><td>${badge(r)}</td></tr>`).join('')}</tbody></table></div><div class="pagination"><span>Records ${reportPage*12+1}–${Math.min(all.length,reportPage*12+12)} of ${all.length}</span><div class="button-row"><button class="button secondary small" id="report-prev" ${reportPage===0?'disabled':''}>Previous</button><button class="button secondary small" id="report-next" ${reportPage===max?'disabled':''}>Next</button></div></div>`:'<div class="empty">No records within this date range.</div>';
}

function renderSettings(){
  $('content').innerHTML=`<div class="settings-grid"><section class="panel">${panelHead('Connect to local MySQL','A separate database named planflow_app_october_2026 will be used')}<form id="mysql-form" class="settings-form"><div class="form-grid"><label>Host<input name="host" value="localhost" required autocomplete="off"></label><label>Port<input name="port" value="3306" type="number" min="1" max="65535" required></label><label>Username<input name="user" placeholder="Your MySQL username" required autocomplete="username"></label><label>Password<input name="password" type="password" placeholder="Your MySQL password" autocomplete="current-password"></label></div><div class="button-row"><button class="button" id="mysql-connect" type="submit">Connect and prepare data</button></div><p class="help">Password stays in this app’s memory until it stops. It is never saved in project files. Enter it again after restarting.</p><div id="connection-result" class="notice" hidden></div></form></section><section class="panel">${panelHead('Your data workspace')}<ul><li>92 days from October to December 2026</li><li>3 departments and 2 shifts</li><li>552 workload and staffing plans</li><li>Scheduled staff and absence counts</li><li>Deadlines and simulated actual performance</li><li>Paid hours, overtime and illustrative costs</li><li>Saved scenarios and an edit audit trail</li></ul><p class="help">A first-time MySQL connection seeds the separate project database. Existing plans and edits are retained in the selected environment.</p></section></div><section class="panel">${panelHead('Recent changes','Local audit records show what was saved')}<div id="audit-list">Loading change history…</div></section>`;
  api('/api/audit').then(data=>{$('audit-list').innerHTML=data.rows.length?data.rows.map(r=>`<div class="audit-item">${esc(r.changed_at.replace('T',' '))} · ${esc(r.action.replaceAll('_',' '))} · record ${r.entity_id}</div>`).join(''):'<p class="help">No edits yet. Changes will appear after saving a plan or scenario.</p>';}).catch(showError);
}
function field(name,label,value,type='number',min=0,max=10000,step=1){return `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${type==='number'?`min="${min}" max="${max}" step="${step}"`:''} required></label>`;}
function selectField(name,label,value,options){return `<label>${label}<select name="${name}">${options.map(([v,t])=>`<option value="${v}" ${String(v)===String(value)?'selected':''}>${esc(t)}</option>`).join('')}</select></label>`;}
function openEditor(id=null,actual=false){
  editRow=id?rows.find(r=>r.plan_id===Number(id)):null;editingActuals=actual;
  const shift=Number($('filter-shift').value), dt=$('filter-date').value;
  const r=editRow||{plan_date:dt,department_id:1,shift_id:shift,forecast_cases:1000,cases_per_person_hour:100,productive_hours:shift===1?6:5.5,scheduled_staff:3,absent_staff:0,paid_hours:8,overtime_hours:0,hourly_cost:14.5,overtime_rate:21.75,dispatch_deadline:dt+(shift===1?'T13:30':'T21:30'),notes:''};
  $('editor-title').textContent=actual?`Actuals · ${r.department_name}`:editRow?`Edit plan · ${r.department_name}`:'Add workload plan';$('form-error').hidden=true;
  if(actual){$('editor-fields').innerHTML=field('actual_cases','Actual cases processed',r.actual_cases??0,'number',0,1000000)+field('actual_staff','Actual staff',r.actual_staff??r.available_staff)+field('actual_productive_hours','Actual productive hours/person',r.actual_productive_hours??r.productive_hours,'number',.01,12,.01)+field('actual_finished_at','Actual finish',r.actual_finished_at||r.dispatch_deadline,'datetime-local');}
  else{$('editor-fields').innerHTML=field('plan_date','Plan date',r.plan_date,'date')+selectField('shift_id','Shift',r.shift_id,meta.shifts.map(x=>[x.shift_id,x.shift_name]))+selectField('department_id','Department',r.department_id,meta.departments.map(x=>[x.department_id,x.department_name]))+field('forecast_cases','Forecast cases',r.forecast_cases,'number',0,1000000)+field('cases_per_person_hour','Cases per person per hour',r.cases_per_person_hour,'number',.01,10000,.01)+field('productive_hours','Productive hours/person',r.productive_hours,'number',.01,12,.01)+field('scheduled_staff','Scheduled staff',r.scheduled_staff)+field('absent_staff','Absent staff',r.absent_staff)+field('paid_hours','Paid shift hours/person',r.paid_hours,'number',.01,12,.01)+field('overtime_hours','Overtime hours/person',r.overtime_hours,'number',0,4,.01)+field('hourly_cost','Hourly cost £',r.hourly_cost,'number',0,1000,.01)+field('overtime_rate','Overtime rate £',r.overtime_rate,'number',0,2000,.01)+field('dispatch_deadline','Dispatch deadline',r.dispatch_deadline,'datetime-local')+`<label>Notes<input name="notes" maxlength="200" value="${esc(r.notes)}"></label>`;}
  $('editor').showModal();
}
$('close-editor').onclick=()=>{$('editor').close();};$('cancel-editor').onclick=()=>{$('editor').close();};
$('editor-form').addEventListener('submit',async e=>{
  e.preventDefault();const btn=e.submitter;btn.disabled=true;$('form-error').hidden=true;
  try{const data=Object.fromEntries(new FormData(e.target));if(editRow)data.version=editRow.version;const route=editingActuals?`/api/plans/${editRow.plan_id}/actuals`:editRow?`/api/plans/${editRow.plan_id}`:'/api/plans';await api(route,editRow?'PUT':'POST',data);$('editor').close();toast('Changes saved.');await load();}
  catch(error){$('form-error').textContent=error.message;$('form-error').hidden=false;}finally{btn.disabled=false;}
});
for(const id of ['filter-date','filter-shift'])$(id).addEventListener('change',()=>{try{localStorage.setItem('planflow-date',$('filter-date').value);localStorage.setItem('planflow-shift',$('filter-shift').value);}catch{}load().catch(showError);});
document.addEventListener('submit',async e=>{
  if(e.target.id==='report-filter-form'){e.preventDefault();clearError();loadReport().catch(showError);}
  if(e.target.id==='mysql-form'){
    e.preventDefault();const btn=$('mysql-connect');btn.disabled=true;clearError();
    try{const values=Object.fromEntries(new FormData(e.target));const result=await api('/api/database/mysql','POST',values);e.target.querySelector('[name="password"]').value='';meta=await api('/api/meta');renderSettings();toast(result.message);}
    catch(error){showError(error);}finally{if($('mysql-connect'))$('mysql-connect').disabled=false;}
  }
});
document.addEventListener('click',async e=>{
  const btn=e.target.closest('button');if(!btn)return;
  try{
    if(btn.dataset.edit){openEditor(btn.dataset.edit);return;}
    if(btn.dataset.actual){openEditor(btn.dataset.actual,true);return;}
    if(btn.dataset.staffSave){const r=rows.find(x=>x.plan_id===Number(btn.dataset.staffSave));btn.disabled=true;await api(`/api/plans/${r.plan_id}`,'PUT',{...r,scheduled_staff:$(`scheduled-${r.plan_id}`).value,absent_staff:$(`absent-${r.plan_id}`).value});toast('Staffing saved.');await load();}
    if(btn.dataset.scenario){renderComparison(await api('/api/scenarios/'+btn.dataset.scenario));window.scrollTo({top:0,behavior:'smooth'});}
    if(btn.id==='add-plan')openEditor();
    if(btn.id==='calculate-scenario'){clearError();btn.disabled=true;await compareScenario();}
    if(btn.id==='cover-forecast'){rows.forEach(r=>{$(`proposed-${r.plan_id}`).value=r.required_staff;});await compareScenario();}
    if(btn.id==='save-scenario'){btn.disabled=true;const result=await api('/api/scenarios','POST',{...scenarioPayload(),scenario_name:$('scenario-name').value});toast(result.message);await savedScenarios();}
    if(btn.id==='export-csv')window.location.href='/api/reports.csv?'+reportQuery();
    if(btn.id==='report-next'){reportPage++;renderReportTable();}
    if(btn.id==='report-prev'){reportPage--;renderReportTable();}
    if(btn.id==='use-demo'){await api('/api/database/demo','POST',{});meta=await api('/api/meta');renderSettings();toast('Using local demo database.');}
  }catch(error){showError(error);}finally{if(btn.isConnected)btn.disabled=false;}
});
async function start(){meta=await api('/api/meta');await load();}
start().catch(showError);
