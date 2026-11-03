const API="https://kaizo-core-engine-production.up.railway.app/api/v1";
const app=document.getElementById("app");
app.innerHTML=[
'<header class="top"><div><div class="brand">KAIZO SYSTEM</div><div id="roleCaption" style="color:#cbd5e1;font-size:13px">Commercial Product Surface · Core preserved</div></div><div class="top-actions"><label class="role-label">Role</label><select id="roleSelect" class="role-select"><option value="coach">Coach</option><option value="academy">Academy</option><option value="athlete">Athlete</option><option value="parent">Parent</option></select><button onclick="kaizoLogin()">Sign in</button><div id="health" class="status">Checking Core…</div></div></header>',
'<main class="wrap"><section id="productNav" class="card span-12 product-nav"></section><section id="roleView" class="card span-12 role-view"></section><div id="coachWorkspace" class="grid">',
'<section id="coach-decision-case" class="card span-12"><h2>Decision Case</h2><div class="row">',
'<div class="field"><label>Case ID</label><input id="caseId"></div><div class="field"><label>Athlete ID</label><input id="athleteId" placeholder="ATH-001"></div>',
'<div class="field"><label>Age Group</label><select id="age"><option>under11</option></select></div><div class="field"><label>Gender</label><select id="gender"><option>male</option></select></div>',
'<div class="field"><label>Weight Category</label><select id="weight"><option>-42kg</option></select></div><div class="field"><label>Metric</label><select id="metric"><option>grip_strength</option></select></div>',
'<div class="field"><label>Actual Value (kg)</label><input id="value" type="number" step="0.1" placeholder="18"></div></div>',
'<div class="row" style="margin-top:12px"><button onclick="evaluateRule()">Evaluate with Core</button><button class="secondary" onclick="health()">Refresh Health</button></div>',
'<div id="evalNote" class="notice" style="margin-top:12px">Coach remains the final authority. Unvalidated numeric claims are blocked by Core.</div><pre id="evalOut" class="output" style="margin-top:12px"></pre></section>',
'<section id="coach-adapt-decision" class="card span-6"><h3>Adapt Decision</h3><div class="row"><div class="field"><label>Operation</label><select id="operation"><option>individual_adaptation</option><option>team_adaptation</option><option>subgroup_recalculation</option><option>individual_change</option></select></div><div class="field"><label>Dynamic Inputs</label><input id="dynamic" value="competition_pressure"></div></div><button style="margin-top:10px" onclick="adapt()">Run Adaptation</button><pre id="adaptOut" class="output" style="margin-top:12px"></pre></section>',
'<section id="coach-decision-loop" class="card span-6"><h3>Decision Loop</h3><div class="row"><div class="field"><label>Decision</label><input id="decision" value="Increase grip-entry decision quality"></div><div class="field"><label>Intervention</label><input id="intervention" value="Constraint-led gripping drill"></div><div class="field"><label>KPI</label><input id="kpi" value="clean entries / 5 reps"></div><div class="field"><label>Retest</label><input id="retest" value="same scenario, independent retest"></div></div><button style="margin-top:10px" onclick="loop()">Complete Loop</button><pre id="loopOut" class="output" style="margin-top:12px"></pre></section>',
'<section id="coach-digital-twin" class="card span-6"><h3>Digital Twin</h3><div class="row"><div class="field"><label>Entity ID</label><input id="entity" value="ATH-001"></div><div class="field"><label>State JSON</label><input id="twinState" value=\'{"readiness":"training","grip":"medium"}\'></div></div><button style="margin-top:10px" onclick="syncTwin()">Sync State</button><button class="secondary" style="margin:10px 0 0 6px" onclick="getTwin()">Read State</button><pre id="twinOut" class="output" style="margin-top:12px"></pre></section>',
'<section id="coach-audit-trail" class="card span-6"><h3>Audit Trail · Restricted</h3><p class="muted">Core currently permits tenant audit reads only for verified Academy principals. Coach action history needs a separate tenant-scoped API; this view does not grant access.</p><button onclick="audit()">Refresh Audit</button><pre id="auditOut" class="output" style="margin-top:12px"></pre></section>
',
'</div></main>'
].join("");
caseId.value="COACH-"+Date.now();
const PRODUCT_API=API+"/product";
const roleSelect=document.getElementById("roleSelect");
roleSelect.addEventListener("change", renderProductRole);
async function productCall(path, opts={}){ const token=await productAccessToken(); opts.headers={...(opts.headers||{}),"Authorization":"Bearer "+token}; const r=await fetch(PRODUCT_API+path,opts); const raw=await r.text(); let j; try{j=raw?JSON.parse(raw):null}catch(_){j={message:"Core returned a non-JSON response",response_excerpt:raw.slice(0,500)}} if(!r.ok) throw new Error("HTTP "+r.status+" "+r.statusText+": "+JSON.stringify(j)); if(j===null) throw new Error("Core returned an empty response for "+path); return j; }
async function kaizoLogin(){try{if(window.KAIZO_AUTH_READY)await window.KAIZO_AUTH_READY;if(!window.KAIZO_AUTH)throw new Error(window.KAIZO_AUTH_INIT_ERROR||"Auth0 SPA is not configured.");await window.KAIZO_AUTH.loginWithRedirect()}catch(e){const view=document.getElementById("roleView");view.textContent=String(e&&e.message?e.message:e)}}
async function productAccessToken(){if(window.KAIZO_AUTH_READY)await window.KAIZO_AUTH_READY;const auth=window.KAIZO_AUTH;if(!auth||typeof auth.getAccessTokenSilently!=="function")throw new Error(window.KAIZO_AUTH_INIT_ERROR||"AUTHENTICATION_REQUIRED: verified Auth0 SPA session is not initialized. Role selection and X-KAIZO headers are not credentials.");const token=await auth.getAccessTokenSilently();if(!token)throw new Error("AUTHENTICATION_REQUIRED: no verified access token was issued.");return token}
function actorForRole(role){return ({coach:"coach-demo",academy:"academy-demo",athlete:"ATH-001",parent:"parent-demo"})[role]}
function ownerForRole(role){return role==="athlete"?"ATH-001":role==="parent"?"ATH-001":role==="coach"?"ATH-001":""}
async function renderProductRole(){ const role=roleSelect.value; document.getElementById("roleCaption").textContent="Commercial Product Surface · "+role+" · execution authorization disabled"; const workspace=document.getElementById("coachWorkspace"); workspace.style.display=role==="coach"?"grid":"none"; try{const nav=await productCall("/navigation"); document.getElementById("productNav").innerHTML="<h3>Product Navigation</h3><div class=\"chips\">"+nav.surfaces.map(x=>"<span class=\"chip\">"+x+"</span>").join("")+"</div><div class=\"governance\">Coach Final Authority: <b>"+nav.coach_final_authority+"</b> · Execution Authorized: <b>"+nav.execution_authorized+"</b></div>"; if(role==="coach"){document.getElementById("roleView").innerHTML=coachDashboard();await loadCoachDashboard();await loadCoachRoster();await loadCoachGroups()} else if(role==="athlete"){const p=await productCall("/athletes/ATH-001/progress?resource_tenant_id=demo-academy");document.getElementById("roleView").innerHTML="<h3>My Progress</h3><pre class=\"output\">"+pretty(p)+"</pre>"} else if(role==="parent"){const p=await productCall("/parents/linked/ATH-001/progress?resource_tenant_id=demo-academy");document.getElementById("roleView").innerHTML="<h3>Linked Athlete Progress</h3><pre class=\"output\">"+pretty(p)+"</pre>"} else {document.getElementById("roleView").innerHTML="<h3>Academy Dashboard</h3><p class=\"muted\">Academy surfaces are tenant-scoped. Group/coach management remains server-authorized.</p>"}}catch(e){const message=String(e&&e.message?e.message:e);document.getElementById("productNav").innerHTML="<h3>Product Navigation</h3><div class=\"notice\">API request failed. Diagnostic details are shown below.</div>";document.getElementById("roleView").innerHTML="<h3>KAIZO request diagnostic</h3><p class=\"notice\">"+escapeHtml(message)+"</p><p class=\"muted\">A frontend/API error is not an authorization decision. Verify the Core response and server-side authorization before closing this issue.</p>"}}
renderProductRole();


async function loadCoachPriorityQueue(){
 const notice=document.getElementById("coachPriorityQueueNotice"),items=document.getElementById("coachPriorityQueueItems");
 if(!notice||!items)return;
 notice.textContent="Loading current evidence-backed review signals…";items.innerHTML="";
 try{
  const data=await productCall("/coach/priority-queue"),rows=Array.isArray(data.items)?data.items:[];
  if(data.status==="INSUFFICIENT_EVIDENCE"||data.available===false){
   notice.textContent=data.message||"Insufficient persisted evidence. No priority items are inferred.";return;
  }
  if(!rows.length){notice.textContent="No current review signals were found in the available workflow records.";return;}
  notice.textContent=rows.length+" evidence-backed review signal(s), not tracked open tasks. Unranked; no calendar-day filter, deadline, or urgency evidence.";
  items.innerHTML=rows.map(item=>'<article class="coach-metric" style="margin:8px 0"><strong>'+escapeHtml(item.title||"Coach review")+'</strong><p>'+escapeHtml(item.athlete_name||item.athlete_id||"")+' · '+escapeHtml(item.item_type||"")+'</p><p>'+escapeHtml(item.reason||"")+'</p><p class="muted">Source: '+escapeHtml(item.source_feature||"")+' / '+escapeHtml(item.source_record_id||"")+' · '+escapeHtml(item.recorded_at||"")+'</p><p class="muted">Evidence: '+escapeHtml((item.evidence_refs||[]).join(", ")||"Source record only")+'</p><p>'+escapeHtml(item.suggested_next_action||"Coach review required.")+'</p><small>Unranked · review status not tracked · Coach judgment required</small></article>').join("");
 }catch(e){notice.textContent="Priority queue unavailable: "+String(e&&e.message?e.message:e);items.textContent="No queue data is displayed when authentication or authorization fails."}
}

async function loadCoachDashboard(){
 const notice=document.getElementById("coachDashboardNotice"),metrics=document.getElementById("coachDashboardMetrics"),recent=document.getElementById("coachDashboardRecent");
 if(!notice||!metrics||!recent)return;
 notice.textContent="Loading verified Coach summary…";metrics.innerHTML="";recent.textContent="";
 try{
  const data=await productCall("/coach/dashboard"),counts=data.athlete_status_counts||{};
  const cards=[
   ["My athletes",data.athlete_total],
   ["Active",counts.ACTIVE||0],
   ["Inactive",counts.INACTIVE||0],
   ["Suspended",counts.SUSPENDED||0],
   ["Archived",counts.ARCHIVED||0],
   ["Training groups",data.training_group_total],
   ["Group memberships",data.group_membership_total],
   ["Recorded decision cycles",data.decision_cycle_total]
  ];
  metrics.innerHTML=cards.map(([label,value])=>'<article class="coach-metric"><span class="muted">'+escapeHtml(label)+'</span><strong>'+escapeHtml(value)+'</strong></article>').join("");
  const items=Array.isArray(data.recent_decisions)?data.recent_decisions:[];
  recent.innerHTML=items.length?items.map(d=>'<article class="coach-metric" style="margin:8px 0"><strong>'+escapeHtml(d.summary||d.decision_id||"Recorded decision")+'</strong><p>'+escapeHtml(d.athlete_name||d.athlete_id||"")+' · '+escapeHtml(d.status||"")+'</p><small>'+escapeHtml(d.recorded_at||"")+' · '+escapeHtml(d.coach_action||"")+'</small></article>').join(""):'<p class="muted">No decision records are currently linked to athletes in your Coach scope.</p>';
  notice.textContent="Verified summary loaded from owned roster, groups and recorded decisions.";
  await loadCoachPriorityQueue();
 }catch(e){notice.textContent="Dashboard summary unavailable: "+String(e&&e.message?e.message:e);metrics.innerHTML="";recent.textContent="No summary data is displayed when authentication or authorization fails."}
}

let coachRosterRecords=[];
let selectedCoachAthleteId=null;

function renderCoachRosterRows(){
 const list=document.getElementById("coachRosterList");
 const search=document.getElementById("athleteRosterSearch");
 if(!list)return;
 const term=(search?.value||"").trim().toLocaleLowerCase();
 const filtered=coachRosterRecords.filter(a=>
  String(a.display_name||"").toLocaleLowerCase().includes(term)||
  String(a.athlete_id||"").toLocaleLowerCase().includes(term));
 if(!coachRosterRecords.length){list.innerHTML='<p class="muted">Your roster is empty. Add an athlete above to establish an audited ownership relation.</p>';return}
 if(!filtered.length){list.innerHTML='<p class="muted">No athletes in your roster match this search.</p>';return}
 list.innerHTML=filtered.map(a=>'<button class="coach-athlete-row" type="button" data-athlete-id="'+escapeHtml(a.athlete_id)+'" onclick="viewCoachAthlete(this.dataset.athleteId)"><span>'+escapeHtml(a.display_name||a.athlete_id)+'</span><small>'+escapeHtml(a.athlete_id)+'</small></button>').join("");
}
function filterCoachRoster(){renderCoachRosterRows()}
function returnCoachRoster(){
 selectedCoachAthleteId=null;
 const panel=document.getElementById("coachAthleteLifecycle"),detail=document.getElementById("coachAthleteDetail"),list=document.getElementById("coachRosterList");
 if(panel)panel.innerHTML="";
 if(detail)detail.textContent="";
 if(list)list.style.display="";
 renderCoachRosterRows();
 const search=document.getElementById("athleteRosterSearch");
 if(search)search.focus();
}
function coachAthleteSection(sectionId){
 const ids=["athleteProfileSection","athleteLifecycleSection","athleteStatusHistorySection","athleteDecisionCyclesSection"];
 if(!ids.includes(sectionId))return;
 ids.forEach(id=>{const el=document.getElementById(id);if(el)el.hidden=id!==sectionId});
 document.querySelectorAll("[data-athlete-section]").forEach(button=>{
  button.setAttribute("aria-pressed",String(button.dataset.athleteSection===sectionId));
 });
}
async function loadCoachRoster(){
  const notice=document.getElementById("coachRosterNotice"),list=document.getElementById("coachRosterList"),detail=document.getElementById("coachAthleteDetail");
  if(!notice||!list)return;
  notice.textContent="Loading your verified Coach roster…";list.innerHTML="";if(detail)detail.textContent="";
  try{
    const result=await productCall("/coach/athletes");
    coachRosterRecords=Array.isArray(result.athletes)?result.athletes:[];
    notice.textContent=coachRosterRecords.length+" athlete(s) assigned to this Coach. Search is limited to this verified roster.";
    const selected=selectedCoachAthleteId;
    if(selected&&!coachRosterRecords.some(a=>String(a.athlete_id)===selected)){returnCoachRoster();renderCoachRosterRows();return;}
    renderCoachRosterRows();
    if(selected)await viewCoachAthlete(selected);
  }catch(e){
    coachRosterRecords=[];selectedCoachAthleteId=null;
    const panel=document.getElementById("coachAthleteLifecycle");if(panel)panel.innerHTML="";
    if(detail)detail.textContent="";
    notice.textContent="Roster unavailable: "+String(e&&e.message?e.message:e);
    list.innerHTML='<p class="muted">No roster data is displayed when authentication or authorization fails.</p>';
  }
}
async function createCoachAthlete(event){
  event.preventDefault();const form=document.getElementById("coachAthleteForm"),notice=document.getElementById("coachRosterNotice"),name=document.getElementById("newAthleteName").value.trim();
  if(!name){notice.textContent="Enter an athlete name.";return}notice.textContent="Creating athlete and ownership record…";
  try{const result=await productCall("/coach/athletes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({display_name:name,metadata:{source:"coach_workspace"}})});
    notice.textContent="Athlete created and assigned to your Coach scope. Audit event recorded.";form.reset();await loadCoachRoster();await viewCoachAthlete(result.athlete_id);
  }catch(e){notice.textContent="Athlete was not created: "+String(e&&e.message?e.message:e)}
}
async function viewCoachAthlete(athleteId){
 const detail=document.getElementById("coachAthleteDetail"),panel=document.getElementById("coachAthleteLifecycle"),list=document.getElementById("coachRosterList");
 if(!coachRosterRecords.some(a=>String(a.athlete_id)===String(athleteId))){
  if(detail)detail.textContent="This athlete is not present in the currently loaded Coach roster.";
  if(panel)panel.innerHTML="";return;
 }
 selectedCoachAthleteId=String(athleteId);
 if(list)list.style.display="none";
 if(detail)detail.textContent="Loading athlete from your verified Coach scope…";
 if(panel)panel.innerHTML="";
 try{
  const result=await productCall("/coach/athletes/"+encodeURIComponent(athleteId));
  if(selectedCoachAthleteId!==String(athleteId))return;
  if(detail)detail.textContent="";
  const next={ACTIVE:["INACTIVE","SUSPENDED","ARCHIVED"],INACTIVE:["ACTIVE","ARCHIVED"],SUSPENDED:["ACTIVE","INACTIVE","ARCHIVED"],ARCHIVED:[]}[String(result.status||"").toUpperCase()]||[];
  const athlete=coachRosterRecords.find(a=>String(a.athlete_id)===String(athleteId));
  panel.innerHTML='<div class="coach-athlete-navigation"><div><p class="muted">My roster / Athlete profile</p><h3>'+escapeHtml(athlete?.display_name||result.display_name||athleteId)+'</h3></div><button class="secondary" type="button" onclick="returnCoachRoster()">Back to my roster</button></div>'+
   '<nav class="coach-athlete-tabs" aria-label="Athlete workflow sections">'+
   '<button type="button" data-athlete-section="athleteProfileSection" aria-pressed="true" onclick="coachAthleteSection(\'athleteProfileSection\')">Profile</button>'+
   '<button type="button" data-athlete-section="athleteLifecycleSection" aria-pressed="false" onclick="coachAthleteSection(\'athleteLifecycleSection\')">Lifecycle</button>'+
   '<button type="button" data-athlete-section="athleteStatusHistorySection" aria-pressed="false" onclick="coachAthleteSection(\'athleteStatusHistorySection\')">Status history</button>'+
   '<button type="button" data-athlete-section="athleteDecisionCyclesSection" aria-pressed="false" onclick="coachAthleteSection(\'athleteDecisionCyclesSection\')">Decision history</button></nav>'+
   '<section id="athleteProfileSection"><h4>Verified athlete profile</h4><pre class="output">'+escapeHtml(pretty(result))+'</pre></section>'+
   '<section id="athleteLifecycleSection" hidden><h4>Athlete lifecycle</h4><p>Current status: <strong>'+escapeHtml(result.status||"Unknown")+'</strong></p>'+
   (next.length?'<label for="athleteNextStatus">Change status</label><select id="athleteNextStatus">'+next.map(s=>'<option value="'+s+'">'+s+'</option>').join("")+'</select><label for="athleteStatusReason">Reason (required)</label><input id="athleteStatusReason" maxlength="500" required placeholder="Record why this status changes"><button type="button" onclick="changeCoachAthleteStatus(\''+escapeHtml(athleteId)+'\')">Save lifecycle change</button>':'<p class="muted">Archived is terminal. No further status transition is permitted.</p>')+'</section>'+
   '<section id="athleteStatusHistorySection" hidden><h4>Status history</h4><div id="athleteStatusHistory">Loading history…</div></section>'+
   '<section id="athleteDecisionCyclesSection" hidden><h4>Decision-cycle history</h4><div id="athleteDecisionCycles">Loading persisted decision cycles…</div></section>';
  loadCoachAthleteStatusHistory(athleteId);
  loadCoachAthleteDecisionCycles(athleteId);
 }catch(e){
  if(selectedCoachAthleteId!==String(athleteId))return;
  if(detail)detail.textContent="Athlete details unavailable: "+String(e&&e.message?e.message:e);
  if(panel)panel.innerHTML='<p class="notice">Athlete details are unavailable outside the verified Coach scope.</p><button class="secondary" type="button" onclick="returnCoachRoster()">Back to my roster</button>';
 }
}
async function changeCoachAthleteStatus(athleteId){
 const panel=document.getElementById("coachAthleteLifecycle"),status=document.getElementById("athleteNextStatus")?.value,reason=document.getElementById("athleteStatusReason")?.value.trim();
 if(!status||!reason){panel.insertAdjacentText("afterbegin","A status and reason are required. ");return}
 try{await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/status",{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status,reason})});await loadCoachRoster();await viewCoachAthlete(athleteId)}
 catch(e){panel.insertAdjacentText("afterbegin","Status change rejected: "+String(e&&e.message?e.message:e)+" ")}
}
async function loadCoachAthleteStatusHistory(athleteId){
 const target=document.getElementById("athleteStatusHistory");if(!target)return;
 try{const data=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/status-history");
  if(selectedCoachAthleteId!==String(athleteId))return;
  target.innerHTML=(data.history||[]).length?data.history.map(h=>'<p><strong>'+escapeHtml(h.previous_status)+' → '+escapeHtml(h.new_status)+'</strong><br><small>'+escapeHtml(h.reason)+' · '+escapeHtml(h.changed_by)+'</small></p>').join(""):'<p class="muted">No status changes recorded.</p>';
 }catch(e){if(selectedCoachAthleteId!==String(athleteId))return;target.textContent="History unavailable: "+String(e&&e.message?e.message:e)}
}

async function loadCoachAthleteDecisionCycles(athleteId){
  const target=document.getElementById("athleteDecisionCycles");if(!target)return;
  target.textContent="Loading persisted decision-cycle history…";
  try{
    const data=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/decision-cycles");
    if(selectedCoachAthleteId!==String(athleteId))return;
    const cycles=Array.isArray(data.cycles)?data.cycles:[];
    if(!cycles.length){target.innerHTML='<p class="muted">No persisted decision cycles are linked to this athlete yet. No historical records have been generated.</p>';return}
    target.innerHTML=cycles.map(c=>'<article class="history-item"><h4>'+escapeHtml(c.decision_summary||c.decision_id)+'</h4><p><strong>'+escapeHtml(c.status||"RECORDED")+'</strong> · '+escapeHtml(c.recorded_at||"")+'</p><p>'+escapeHtml(c.outcome_intent||"")+'</p><p class="muted">Decision: '+escapeHtml(c.decision_id)+' · Coach action: '+escapeHtml(c.coach_action||"")+'</p>'+
      '<p><strong>Training records ('+(c.training_records||[]).length+')</strong></p>'+
      ((c.training_records||[]).length?(c.training_records||[]).map(r=>'<p class="muted">'+escapeHtml(r.feature_id||"")+' · '+escapeHtml(r.session_id||r.record_id||"")+' · '+escapeHtml(r.created_at||"")+'</p>').join(""):'<p class="muted">No linked training workflow records.</p>')+
      '<p><strong>Training plans ('+(c.training_plans||[]).length+')</strong></p>'+
      ((c.training_plans||[]).length?(c.training_plans||[]).map(p=>'<p class="muted">'+escapeHtml(p.title||p.plan_id)+' · '+escapeHtml(p.status||"")+'</p>').join(""):'<p class="muted">No linked training plans.</p>')+'</article>').join("");
  }catch(e){if(selectedCoachAthleteId!==String(athleteId))return;target.textContent="Decision history unavailable: "+String(e&&e.message?e.message:e)}
}
\nfunction coachGo(id){const target=document.getElementById(id);if(target){target.scrollIntoView({behavior:"smooth",block:"start"});target.setAttribute("tabindex","-1");target.focus({preventScroll:true})}}
function coachDashboard(){return `
<div class="coach-dashboard">
  <div class="coach-dashboard-head"><div><h2>Coach Home</h2><p class="muted">Decision support and workflow navigation. Coach retains final authority; execution remains disabled unless Core authorizes it.</p></div><span class="coach-state">CORE-GOVERNED</span></div>
  <section class="coach-dashboard-summary" aria-live="polite">
    <div class="coach-roster-head"><div><h3>Verified coaching overview</h3><p class="muted">Counts are calculated from records owned by your authenticated Coach account and tenant.</p></div><button class="secondary" type="button" onclick="loadCoachDashboard()">Refresh overview</button></div>
    <div id="coachDashboardNotice" class="notice" role="status">Loading verified Coach summary…</div>
    <div id="coachDashboardMetrics" class="coach-metrics"></div>
    <h4>Recent recorded decisions</h4><div id="coachDashboardRecent"></div>
  </section>
  <section id="coachPriorityQueue" class="coach-dashboard-summary" aria-live="polite">
    <div class="coach-roster-head"><div><h3>Current review signals</h3><p class="muted">Only explicit workflow evidence is shown. This is not a tracked open-task list or calendar-day filter; items are unranked and have no inferred deadlines.</p></div><button class="secondary" type="button" onclick="loadCoachPriorityQueue()">Refresh queue</button></div>
    <div id="coachPriorityQueueNotice" class="notice" role="status">Loading current review signals…</div>
    <div id="coachPriorityQueueItems"></div>
  </section>
  <div class="coach-metrics">
    <article class="coach-metric"><span class="muted">Decision cycle</span><strong>Ready to enter</strong><small>Evaluate → adapt → intervene → retest.</small></article>
    <article class="coach-metric"><span class="muted">Audit review</span><strong>Authorization required</strong><small>Audit requests must be verified by Core; failures are shown, not hidden.</small></article>
  </div>
  <section id="coach-roster" class="coach-roster"><div class="coach-roster-head"><div><h3>My Athlete Roster</h3><p class="muted">Only athletes assigned to the authenticated coach in the authenticated tenant are shown.</p></div><button class="secondary" onclick="loadCoachRoster()">Refresh roster</button></div><form id="coachAthleteForm" class="coach-roster-form" onsubmit="createCoachAthlete(event)"><label for="newAthleteName">Athlete name</label><input id="newAthleteName" name="display_name" maxlength="120" required placeholder="Enter athlete name"><button type="submit">Add athlete to my roster</button></form><div class="coach-roster-form"><label for="athleteRosterSearch">Search my athletes</label><input id="athleteRosterSearch" type="search" maxlength="120" placeholder="Search by name or athlete ID" oninput="filterCoachRoster()"><button class="secondary" type="button" onclick="returnCoachRoster()">Back to roster</button></div><div id="coachRosterNotice" class="notice" role="status">Sign in with a verified Coach account to load your roster.</div><div id="coachRosterList" class="coach-roster-list"></div><pre id="coachAthleteDetail" class="output" aria-live="polite"></pre><div id="coachAthleteLifecycle" class="coach-roster" aria-live="polite"></div></section><section id="coach-groups" class="coach-roster"><div class="coach-roster-head"><div><h3>My Training Groups</h3><p class="muted">Groups and membership are restricted to your verified Coach and tenant scope.</p></div><button class="secondary" onclick="loadCoachGroups()">Refresh groups</button></div><form class="coach-roster-form" onsubmit="createCoachGroup(event)"><label for="newCoachGroupName">Group name</label><input id="newCoachGroupName" maxlength="100" required placeholder="e.g. U15 competition group"><button type="submit">Create group</button></form><div class="row"><label for="groupAthleteSelect">My athlete</label><select id="groupAthleteSelect"><option value="">Load your roster first</option></select></div><div id="coachGroupsNotice" class="notice" role="status">Sign in as Coach to load your groups.</div><div id="coachGroupsList"></div></section><h3>Open Coach workflow</h3>
  <div class="coach-actions">
    <button onclick="coachGo('coach-decision-case')">1. Evaluate athlete</button>
    <button onclick="coachGo('coach-adapt-decision')">2. Adapt decision</button>
    <button onclick="coachGo('coach-decision-loop')">3. Record intervention & retest</button>
    <button class="secondary" onclick="coachGo('coach-digital-twin')">4. Review athlete state</button>
    <button class="secondary" onclick="coachGo('coach-audit-trail')">5. Check audit access</button>
    <button class="secondary" onclick="coachGo('coach-action-history')">6. Review my actions</button>
  </div>
  <p class="notice coach-honesty">Athlete navigation uses the verified Coach roster and existing scoped profile, lifecycle, status-history, and decision-history records. Coach remains the final authority.</p>
</div>` }

async function call(path,opts){const r=await fetch(API+path,opts||{});const j=await r.json();if(!r.ok)throw new Error(JSON.stringify(j));return j}
function escapeHtml(value){return String(value).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;")}
function pretty(x){return JSON.stringify(x,null,2)}
async function health(){try{const j=await call("/health");healthEl.textContent="CORE ONLINE";healthEl.style.background="#166534";return j}catch(e){healthEl.textContent="CORE UNREACHABLE";healthEl.style.background="#991b1b";return {error:String(e)}}}
const healthEl=document.getElementById("health");
async function evaluateRule(){const j=await call("/rules/evaluate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({athlete_id:athleteId.value||"UNSET",age_group:age.value,gender:gender.value,weight_category:weight.value,metric_name:metric.value,actual_value:value.value===""?null:Number(value.value)})});evalOut.textContent=pretty(j);evalNote.textContent=j.status==="HOLD"?"HOLD: Core blocked the path; review diagnostics.":"Decision returned by Core; Coach retains final authority."}
async function adapt(){const j=await call("/decision/adapt",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({case_id:caseId.value,operation:operation.value,common_core:{goal:"coach decision support"},dynamic_inputs:{context:dynamic.value},coach_final_authority:true})});adaptOut.textContent=pretty(j)}
async function loop(){const j=await call("/decision/loop",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({case_id:caseId.value,decision:{text:decision.value},intervention:{text:intervention.value},response_kpi:{metric:kpi.value},retest:{method:retest.value},coach_final_authority:true})});loopOut.textContent=pretty(j)}
async function syncTwin(){let s;try{s=JSON.parse(twinState.value)}catch(e){twinOut.textContent="Invalid JSON";return}const j=await call("/digital-twin/sync",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({case_id:caseId.value,entity_id:entity.value,state:s,source_event:"coach_workspace_update",coach_final_authority:true})});twinOut.textContent=pretty(j)}
async function getTwin(){const j=await call("/digital-twin/"+encodeURIComponent(entity.value));twinOut.textContent=pretty(j)}
async function audit(){try{const token=await productAccessToken();const r=await fetch(API+"/audit/logs",{headers:{"Authorization":"Bearer "+token}});const raw=await r.text();let j;try{j=raw?JSON.parse(raw):null}catch(_){j={message:"Core returned a non-JSON response",response_excerpt:raw.slice(0,500)}}if(!r.ok)throw new Error("HTTP "+r.status+" "+r.statusText+": "+JSON.stringify(j));auditOut.textContent=pretty(j)}catch(e){auditOut.textContent=String(e&&e.message?e.message:e)}}

health();

async function loadCoachGroups(){
 const notice=document.getElementById("coachGroupsNotice"),list=document.getElementById("coachGroupsList"),select=document.getElementById("groupAthleteSelect");
 if(!notice||!list||!select)return;
 notice.textContent="Loading Coach-owned groups and roster…";list.innerHTML="";
 try{
  const [g,r]=await Promise.all([productCall("/coach/groups"),productCall("/coach/athletes")]);
  select.innerHTML='<option value="">Select an athlete</option>'+(r.athletes||[]).map(a=>'<option value="'+escapeHtml(a.athlete_id)+'">'+escapeHtml(a.display_name||a.athlete_id)+'</option>').join("");
  const groups=g.groups||[];notice.textContent=groups.length+" training group(s) in your Coach scope.";
  if(!groups.length){list.innerHTML='<p class="muted">No groups yet. Create your first training group above.</p>';return}
  list.innerHTML=groups.map(group=>'<article class="coach-metric" style="margin:10px 0"><h4>'+escapeHtml(group.name)+'</h4><small>'+((group.athletes||[]).length)+' athlete(s)</small><button type="button" onclick="assignCoachGroupAthlete(\''+escapeHtml(group.group_id)+'\')">Add selected athlete</button><div>'+((group.athletes||[]).map(a=>'<div class="coach-athlete-row"><span>'+escapeHtml(a.display_name||a.athlete_id)+'</span><button class="secondary" type="button" onclick="unassignCoachGroupAthlete(\''+escapeHtml(group.group_id)+'\',\''+escapeHtml(a.athlete_id)+'\')">Remove</button></div>').join(""))+'</div></article>').join("");
 }catch(e){notice.textContent="Training groups unavailable: "+String(e&&e.message?e.message:e);list.innerHTML='<p class="muted">No group data is shown when authentication or authorization fails.</p>'}
}
async function createCoachGroup(event){
 event.preventDefault();const name=document.getElementById("newCoachGroupName").value.trim(),notice=document.getElementById("coachGroupsNotice");
 try{await productCall("/coach/groups",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name})});document.getElementById("newCoachGroupName").value="";notice.textContent="Group created. Tenant-scoped audit event recorded.";await loadCoachGroups()}
 catch(e){notice.textContent="Group was not created: "+String(e&&e.message?e.message:e)}
}
async function assignCoachGroupAthlete(groupId){
 const athleteId=document.getElementById("groupAthleteSelect").value,notice=document.getElementById("coachGroupsNotice");
 if(!athleteId){notice.textContent="Select an athlete from your own roster first.";return}
 try{await productCall("/coach/groups/"+encodeURIComponent(groupId)+"/athletes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({athlete_id:athleteId})});notice.textContent="Athlete assigned to group. Audit event recorded.";await loadCoachGroups()}
 catch(e){notice.textContent="Assignment denied or failed: "+String(e&&e.message?e.message:e)}
}
async function unassignCoachGroupAthlete(groupId,athleteId){
 const notice=document.getElementById("coachGroupsNotice");
 try{await productCall("/coach/groups/"+encodeURIComponent(groupId)+"/athletes/"+encodeURIComponent(athleteId),{method:"DELETE"});notice.textContent="Athlete removed from group. Audit event recorded.";await loadCoachGroups()}
 catch(e){notice.textContent="Removal denied or failed: "+String(e&&e.message?e.message:e)}
}
