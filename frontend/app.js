const API=window.KAIZO_API_BASE || "/api/v1";
const app=document.getElementById("app");
app.innerHTML=[
'<header class="top"><div><div class="brand">KAIZO SYSTEM</div><div id="roleCaption" style="color:#cbd5e1;font-size:13px">Commercial Product Surface · Core preserved</div></div><div class="top-actions"><label class="role-label">Role</label><select id="roleSelect" class="role-select"><option value="coach">Coach</option><option value="academy">Academy</option><option value="athlete">Athlete</option><option value="parent">Parent</option></select><button onclick="kaizoLogin()">Sign in</button><div id="health" class="status">Checking Core…</div></div></header>',
'<main class="wrap"><section id="productNav" class="card span-12 product-nav"></section><section id="roleView" class="card span-12 role-view"></section></main>'
].join("");
const PRODUCT_API=API+"/product";
const roleSelect=document.getElementById("roleSelect");
roleSelect.addEventListener("change", renderProductRole);
async function productCall(path, opts={}){ const token=await productAccessToken(); opts.headers={...(opts.headers||{}),"Authorization":"Bearer "+token}; const r=await fetch(PRODUCT_API+path,opts); const raw=await r.text(); let j; try{j=raw?JSON.parse(raw):null}catch(_){j={message:"Core returned a non-JSON response",response_excerpt:raw.slice(0,500)}} if(!r.ok) throw new Error("HTTP "+r.status+" "+r.statusText+": "+JSON.stringify(j)); if(j===null) throw new Error("Core returned an empty response for "+path); return j; }
async function stateCycleCall(path, opts={}){ const token=await productAccessToken(); opts.headers={...(opts.headers||{}),"Authorization":"Bearer "+token}; const r=await fetch(API+path,opts); const raw=await r.text(); let j; try{j=raw?JSON.parse(raw):null}catch(_){j={message:"Core returned a non-JSON response",response_excerpt:raw.slice(0,500)}} if(!r.ok) throw new Error("HTTP "+r.status+" "+r.statusText+": "+JSON.stringify(j)); if(j===null) throw new Error("Core returned an empty response for "+path); return j; }
async function kaizoLogin(){try{if(window.KAIZO_AUTH_READY)await window.KAIZO_AUTH_READY;if(!window.KAIZO_AUTH)throw new Error(window.KAIZO_AUTH_INIT_ERROR||"Auth0 SPA is not configured.");await window.KAIZO_AUTH.loginWithRedirect()}catch(e){const view=document.getElementById("roleView");view.textContent=String(e&&e.message?e.message:e)}}
async function productAccessToken(){if(window.KAIZO_AUTH_READY)await window.KAIZO_AUTH_READY;const auth=window.KAIZO_AUTH;if(!auth||typeof auth.getAccessTokenSilently!=="function")throw new Error(window.KAIZO_AUTH_INIT_ERROR||"AUTHENTICATION_REQUIRED: verified Auth0 SPA session is not initialized. Role selection and X-KAIZO headers are not credentials.");const token=await auth.getAccessTokenSilently();if(!token)throw new Error("AUTHENTICATION_REQUIRED: no verified access token was issued.");return token}
function actorForRole(role){return ({coach:"coach-demo",academy:"academy-demo",athlete:"ATH-001",parent:"parent-demo"})[role]}
function ownerForRole(role){return role==="athlete"?"ATH-001":role==="parent"?"ATH-001":role==="coach"?"ATH-001":""}
async function renderProductRole(){ const role=roleSelect.value; document.getElementById("roleCaption").textContent="Commercial Product Surface · "+role+" · execution authorization disabled"; try{const nav=await productCall("/navigation"); document.getElementById("productNav").innerHTML="<h3>Product Navigation</h3><div class=\"chips\">"+nav.surfaces.map(x=>"<span class=\"chip\">"+x+"</span>").join("")+"</div><div class=\"governance\">Coach Final Authority: <b>"+nav.coach_final_authority+"</b> · Execution Authorized: <b>"+nav.execution_authorized+"</b></div>"; if(role==="coach"){document.getElementById("roleView").innerHTML=coachDashboard();await loadCoachDashboard();await loadCoachRoster();await loadCoachGroups()} else if(role==="athlete"){const p=await productCall("/athletes/ATH-001/progress?resource_tenant_id=demo-academy");document.getElementById("roleView").innerHTML="<h3>My Progress</h3><pre class=\"output\">"+pretty(p)+"</pre>"} else if(role==="parent"){const p=await productCall("/parents/linked/ATH-001/progress?resource_tenant_id=demo-academy");document.getElementById("roleView").innerHTML="<h3>Linked Athlete Progress</h3><pre class=\"output\">"+pretty(p)+"</pre>"} else {document.getElementById("roleView").innerHTML="<h3>Academy Dashboard</h3><p class=\"muted\">Academy surfaces are tenant-scoped. Group/coach management remains server-authorized.</p>"}}catch(e){const message=String(e&&e.message?e.message:e);document.getElementById("productNav").innerHTML="<h3>Product Navigation</h3><div class=\"notice\">API request failed. Diagnostic details are shown below.</div>";document.getElementById("roleView").innerHTML="<h3>KAIZO request diagnostic</h3><p class=\"notice\">"+escapeHtml(message)+"</p><p class=\"muted\">A frontend/API error is not an authorization decision. Verify the Core response and server-side authorization before closing this issue.</p>"}}
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
let currentCoachDecisionCycleId=null;
let currentCoachAssessmentId=null;
let currentCoachKpiId=null;
let currentCoachKpiCaptureId=null;
let currentCoachProblemId=null;
let currentCoachDiagnosisId=null;
let currentCoachCandidateId=null;
let currentCoachDecisionId=null;
let currentCoachPlanId=null;
let currentCoachSessionId=null;
let currentCoachLibraryItemId=null;

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
 const ids=["athleteProfileSection","athleteAssessmentSection","athleteProblemAnalysisSection","athleteLifecycleSection","athleteStatusHistorySection","athleteDecisionCyclesSection","athleteDecisionExecutionSection","coachDigitalTwinSection","athleteDecisionWorkspaceSection","athleteActionHistorySection","athleteAuditReviewSection"];
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
 currentCoachDecisionCycleId=null;
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
   '<button type="button" data-athlete-section="athleteAssessmentSection" aria-pressed="false" onclick="coachAthleteSection(&quot;athleteAssessmentSection&quot;)">Assessment & KPIs</button>'+
   '<button type="button" data-athlete-section="athleteProblemAnalysisSection" aria-pressed="false" onclick="coachAthleteSection(&quot;athleteProblemAnalysisSection&quot;)">Problem analysis</button>'+
   '<button type="button" data-athlete-section="athleteLifecycleSection" aria-pressed="false" onclick="coachAthleteSection(\'athleteLifecycleSection\')">Lifecycle</button>'+
   '<button type="button" data-athlete-section="athleteStatusHistorySection" aria-pressed="false" onclick="coachAthleteSection(\'athleteStatusHistorySection\')">Status history</button>'+
   '<button type="button" data-athlete-section="athleteDecisionCyclesSection" aria-pressed="false" onclick="coachAthleteSection(\'athleteDecisionCyclesSection\')">Decision history</button>'+
   '<button type="button" data-athlete-section="athleteDecisionExecutionSection" aria-pressed="false" onclick="coachAthleteSection(&quot;athleteDecisionExecutionSection&quot;)">Decision & adaptation</button>'+
   '<button type="button" data-athlete-section="athleteDecisionWorkspaceSection" aria-pressed="false" onclick="coachAthleteSection(&quot;athleteDecisionWorkspaceSection&quot;)">Decision workspace</button>'+
   '<button type="button" data-athlete-section="athleteActionHistorySection" aria-pressed="false" onclick="coachAthleteSection(&quot;athleteActionHistorySection&quot;)">Action history</button>'+
   '<button type="button" data-athlete-section="athleteAuditReviewSection" aria-pressed="false" onclick="coachAthleteSection(&quot;athleteAuditReviewSection&quot;)">Audit review</button></nav>'+
   '<section id="athleteProfileSection"><h4>Verified athlete profile</h4><pre class="output">'+escapeHtml(pretty(result))+'</pre></section>'+
   '<section id="athleteAssessmentSection" hidden><h4>Assessment, KPI, evidence & state baseline (FEAT-011–015)</h4><p class="muted">All operations use the selected athlete and the protected Coach Product API. The server verifies Bearer identity, tenant, athlete ownership, dependency lineage, and audit. No execution is authorized.</p><div id="coachAssessmentNotice" class="notice">Loading owned assessments…</div><div class="coach-roster-form"><label for="coachAssessmentSelect">Owned assessment</label><select id="coachAssessmentSelect" onchange="selectCoachAssessment(this.value)"><option value="">Select an assessment</option></select><div id="coachAssessmentList"></div></div><form id="coachAssessmentForm" class="coach-roster-form" onsubmit="createCoachAssessment(event)"><h5>Record assessment measurements</h5><label for="coachAssessmentTemplateId">Assessment template</label><input id="coachAssessmentTemplateId" maxlength="120" required placeholder="e.g. U15-GRIP-BASELINE"><label for="coachAssessmentMeasurements">Measurements (JSON object)</label><textarea id="coachAssessmentMeasurements" rows="4" required>{\"grip_strength_kg\":18.5,\"entry_quality\":7}</textarea><button type="submit">Save assessment</button></form><form id="coachKpiDefinitionForm" class="coach-roster-form" onsubmit="createCoachKpiDefinition(event)"><h5>Define Coach-scoped KPI</h5><label for="coachKpiDefinitionId">KPI ID</label><input id="coachKpiDefinitionId" maxlength="120" required placeholder="e.g. GRIP-STRENGTH"><label for="coachKpiDefinitionName">Name</label><input id="coachKpiDefinitionName" maxlength="120" required placeholder="Grip strength"><label for="coachKpiMetricName">Metric name</label><input id="coachKpiMetricName" maxlength="120" required placeholder="grip_strength"><label for="coachKpiUnit">Unit</label><input id="coachKpiUnit" maxlength="40" required placeholder="kg"><label for="coachKpiTarget">Target (optional)</label><input id="coachKpiTarget" type="number" step="any" placeholder="25"><label for="coachKpiDirection">Direction</label><select id="coachKpiDirection"><option value="higher_is_better">Higher is better</option><option value="lower_is_better">Lower is better</option><option value="target_range">Target range</option></select><button type="submit">Save KPI definition</button></form><form id="coachKpiCaptureForm" class="coach-roster-form" onsubmit="createCoachKpiCapture(event)"><h5>Capture KPI for selected assessment</h5><label for="coachKpiCaptureId">Coach-scoped KPI ID</label><input id="coachKpiCaptureId" maxlength="120" required placeholder="Create or enter your KPI ID"><label for="coachKpiCaptureValue">Observed value</label><input id="coachKpiCaptureValue" type="number" step="any" required><button type="submit">Save KPI capture</button></form><form id="coachEvidenceForm" class="coach-roster-form" onsubmit="attachCoachAssessmentEvidence(event)"><h5>Attach existing evidence</h5><label for="coachAssessmentEvidenceId">Persisted evidence ID</label><input id="coachAssessmentEvidenceId" maxlength="160" required placeholder="Existing assessment evidence reference"><button type="submit">Attach evidence to selected assessment</button></form><form id="coachStateSnapshotForm" class="coach-roster-form" onsubmit="createCoachStateSnapshot(event)"><h5>Create baseline / current-state snapshot</h5><label for="coachSnapshotType">Snapshot type</label><select id="coachSnapshotType"><option value="baseline">Baseline</option><option value="current_state">Current state</option></select><label for="coachKpiCaptureIds">KPI capture IDs (comma-separated)</label><input id="coachKpiCaptureIds" maxlength="1000" required placeholder="Capture IDs from the KPI capture response"><button type="submit">Save state snapshot</button></form><pre id="coachAssessmentOutput" class="output" aria-live="polite"></pre></section>'+
   '<section id="athleteProblemAnalysisSection" hidden><h4>Problem analysis and diagnosis (FEAT-016–020)</h4><p class="muted">Create a problem statement from an owned assessment, record cause/context, and create an evidence-linked diagnosis. Only verified evidence linked to this athlete, problem, or assessment is accepted. The Coach remains the final authority; execution is not authorized.</p><div id="coachProblemLibraryNotice" class="notice">Only provenance-bearing APPROVED and VERIFIED problem entries are selectable.</div><button type="button" onclick="loadCoachProblemLibrary()">Load approved problem library</button><label for="coachProblemLibrarySelect">Approved problem library entry</label><select id="coachProblemLibrarySelect" onchange="selectCoachProblemLibraryItem(this.value)"><option value="">Load and select a problem entry</option></select><button type="button" onclick="createCoachProblemLibrarySelection()">Attach selected problem to current assessment</button><button type="button" onclick="loadCoachProblemLibrarySelections()">Read selections for current assessment</button><pre id="coachProblemLibraryOutput" class="output" aria-live="polite"></pre><div id="coachProblemNotice" class="notice">Loading owned problem records…</div><label for="coachProblemSelect">Owned problem statement</label><select id="coachProblemSelect" onchange="selectCoachProblem(this.value)"><option value="">Select a problem</option></select><form id="coachProblemStatementForm" class="coach-roster-form" onsubmit="createCoachProblemStatement(event)"><h5>Create structured problem statement</h5><label for="coachProblemStatement">Problem statement</label><textarea id="coachProblemStatement" rows="3" required maxlength="1200" placeholder="Describe the observable performance problem"></textarea><label for="coachProblemType">Problem type</label><input id="coachProblemType" required maxlength="120" placeholder="e.g. technical_execution"><label for="coachProblemImpact">Impact (optional)</label><input id="coachProblemImpact" maxlength="500" placeholder="Effect on performance"><button type="submit">Save problem statement</button></form><form id="coachCauseContextForm" class="coach-roster-form" onsubmit="createCoachCauseContext(event)"><h5>Cause and context framing (FEAT-018)</h5><label for="coachProblemCause">Cause</label><textarea id="coachProblemCause" rows="2" required maxlength="1200" placeholder="Describe the likely cause"></textarea><label for="coachProblemContext">Context (JSON object)</label><textarea id="coachProblemContext" rows="3">{}</textarea><label for="coachProblemFactors">Contributing factors (comma-separated)</label><input id="coachProblemFactors" maxlength="1000" placeholder="distance, timing, grip"><button type="submit">Save cause/context</button></form><form id="coachDiagnosisForm" class="coach-roster-form" onsubmit="createCoachDiagnosis(event)"><h5>Evidence-linked diagnosis (FEAT-019/020)</h5><label for="coachDiagnosisText">Diagnosis</label><textarea id="coachDiagnosisText" rows="2" required maxlength="1200" placeholder="Describe the evidence-supported diagnosis"></textarea><label for="coachDiagnosisEvidenceIds">Verified evidence IDs (comma-separated)</label><input id="coachDiagnosisEvidenceIds" required maxlength="1000" placeholder="EVID-001, EVID-002"><label for="coachDiagnosisConfidence">Confidence</label><select id="coachDiagnosisConfidence"><option value="">Not assessed</option><option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH">High</option></select><label for="coachDiagnosisResolution">Resolution state</label><select id="coachDiagnosisResolution"><option value="UNRESOLVED">Unresolved</option><option value="RESOLVED">Resolved</option></select><button type="submit">Save diagnosis</button></form><div id="coachDecisionNotice" class="notice">Decision candidates remain subject to explicit Coach review.</div><button type="button" onclick="generateCoachDecisionCandidates()">Generate decision candidates</button><label for="coachCandidateSelect">Decision candidate</label><select id="coachCandidateSelect" onchange="selectCoachCandidate(this.value)"><option value="">Generate or select a candidate</option></select><form id="coachDecisionRationaleForm" class="coach-roster-form" onsubmit="recordCoachDecisionRationale(event)"><h5>Record evidence-linked rationale (FEAT-022)</h5><label for="coachDecisionRationale">Rationale</label><textarea id="coachDecisionRationale" rows="2" required maxlength="1200"></textarea><label for="coachDecisionRationaleEvidence">Verified evidence IDs (comma-separated)</label><input id="coachDecisionRationaleEvidence" required maxlength="1000" placeholder="EVID-001, EVID-002"><button type="submit">Save rationale</button></form><form id="coachDecisionComparisonForm" class="coach-roster-form" onsubmit="compareCoachDecisionCandidates(event)"><h5>Compare alternatives (FEAT-023)</h5><label for="coachCompareCandidateA">First candidate</label><select id="coachCompareCandidateA" required><option value="">Select candidate</option></select><label for="coachCompareCandidateB">Second candidate</label><select id="coachCompareCandidateB" required><option value="">Select candidate</option></select><button type="submit">Compare alternatives</button></form><form id="coachDecisionReviewForm" class="coach-roster-form" onsubmit="reviewCoachDecisionCandidate(event)"><h5>Coach Final Authority review (FEAT-024)</h5><label for="coachDecisionReviewAction">Coach action</label><select id="coachDecisionReviewAction"><option value="CONFIRM">Confirm</option><option value="OVERRIDE">Override</option></select><label for="coachDecisionOverrideReason">Override reason (required for override)</label><input id="coachDecisionOverrideReason" maxlength="1000" placeholder="Why the Coach selects a different option"><button type="submit">Save Coach review</button></form><form id="coachDecisionRecordForm" class="coach-roster-form" onsubmit="recordCoachDecision(event)"><h5>Record final Coach decision (FEAT-025)</h5><label for="coachDecisionOutcomeIntent">Outcome intent</label><textarea id="coachDecisionOutcomeIntent" rows="2" required maxlength="1200"></textarea><label for="coachDecisionSummary">Decision summary (optional)</label><input id="coachDecisionSummary" maxlength="500"><button type="submit">Record decision after Coach review</button></form><pre id="coachDecisionWorkflowOutput" class="output" aria-live="polite"></pre><div id="coachTrainingNotice" class="notice">Training artefacts are draft proposals and are never executed by this workflow.</div><form id="coachTrainingPlanForm" class="coach-roster-form" onsubmit="createCoachTrainingPlan(event)"><h5>Draft training plan (FEAT-026)</h5><label for="coachTrainingPlanTitle">Plan title</label><input id="coachTrainingPlanTitle" required maxlength="200"><label for="coachTrainingPlanObjective">Objective</label><textarea id="coachTrainingPlanObjective" rows="2" required maxlength="1200"></textarea><label for="coachTrainingPlanConstraints">Constraints (JSON object)</label><textarea id="coachTrainingPlanConstraints" rows="2">{}</textarea><button type="submit">Save draft plan</button></form><label for="coachTrainingPlanSelect">Owned training plan</label><select id="coachTrainingPlanSelect" onchange="selectCoachTrainingPlan(this.value)"><option value="">Select a draft plan</option></select><form id="coachTrainingSessionForm" class="coach-roster-form" onsubmit="createCoachTrainingSession(event)"><h5>Draft session structure (FEAT-027)</h5><label for="coachTrainingSessionTitle">Session title</label><input id="coachTrainingSessionTitle" required maxlength="200"><label for="coachTrainingSessionDuration">Total duration (minutes)</label><input id="coachTrainingSessionDuration" type="number" min="1" required><label for="coachTrainingSessionBlocks">Blocks (JSON array; each block needs name and duration_minutes)</label><textarea id="coachTrainingSessionBlocks" rows="4" required>[{"name":"Uchi-komi timing","duration_minutes":20},{"name":"Resistance randori","duration_minutes":20}]</textarea><button type="submit">Save draft session</button></form><label for="coachTrainingSessionSelect">Owned session</label><select id="coachTrainingSessionSelect" onchange="selectCoachTrainingSession(this.value)"><option value="">Select a session</option></select><form id="coachTrainingDosageForm" class="coach-roster-form" onsubmit="createCoachTrainingDosage(event)"><h5>Draft dosage prescription (FEAT-028)</h5><label for="coachTrainingDosageBlock">Existing session block name</label><input id="coachTrainingDosageBlock" required maxlength="160"><label for="coachTrainingDosageSets">Sets</label><input id="coachTrainingDosageSets" type="number" min="1" required><label for="coachTrainingDosageReps">Reps</label><input id="coachTrainingDosageReps" type="number" min="1" required><label for="coachTrainingDosageRest">Rest (seconds)</label><input id="coachTrainingDosageRest" type="number" min="0" value="0"><label for="coachTrainingDosageNotes">Notes</label><input id="coachTrainingDosageNotes" maxlength="500"><button type="submit">Save draft dosage</button></form><pre id="coachTrainingWorkflowOutput" class="output" aria-live="polite"></pre><pre id="coachProblemAnalysisOutput" class="output" aria-live="polite"></pre></section>'+
   '<section id="athleteLifecycleSection" hidden><h4>Athlete lifecycle</h4><p>Current status: <strong>'+escapeHtml(result.status||"Unknown")+'</strong></p>'+
   (next.length?'<label for="athleteNextStatus">Change status</label><select id="athleteNextStatus">'+next.map(s=>'<option value="'+s+'">'+s+'</option>').join("")+'</select><label for="athleteStatusReason">Reason (required)</label><input id="athleteStatusReason" maxlength="500" required placeholder="Record why this status changes"><button type="button" onclick="changeCoachAthleteStatus(\''+escapeHtml(athleteId)+'\')">Save lifecycle change</button>':'<p class="muted">Archived is terminal. No further status transition is permitted.</p>')+'</section>'+
   '<section id="athleteStatusHistorySection" hidden><h4>Status history</h4><div id="athleteStatusHistory">Loading history…</div></section>'+
   '<section id="athleteDecisionCyclesSection" hidden><h4>Decision-cycle history</h4><div id="athleteDecisionCycles">Loading persisted decision cycles…</div></section>'+
   '<section id="athleteDecisionExecutionSection" hidden><h4>Coach decision and adaptation</h4><p class="muted">This creates a durable, athlete-scoped decision cycle and records adaptation against its exact ID. Coach Final Authority remains active; execution is not authorized.</p><form id="coachDecisionCycleForm" class="coach-roster-form" onsubmit="createCoachDecisionCycle(event)"><label for="coachDecisionCaseId">Case reference</label><input id="coachDecisionCaseId" maxlength="120" required placeholder="e.g. U15-CASE-001"><label for="coachDecisionChoice">Coach decision</label><input id="coachDecisionChoice" maxlength="500" required placeholder="Describe the selected coaching decision"><label for="coachIntervention">Planned intervention</label><input id="coachIntervention" maxlength="500" required placeholder="Describe the intervention"><label for="coachResponseKpi">Response / KPI observation</label><input id="coachResponseKpi" maxlength="500" required placeholder="Record the observed response"><label for="coachRetest">Retest result</label><input id="coachRetest" maxlength="500" required placeholder="Record the retest result"><button type="submit">Save decision cycle</button></form><div id="coachDecisionCycleNotice" class="notice">Select an athlete and record the Coach decision.</div><pre id="coachDecisionCycleReadback" class="output"></pre><form id="coachAdaptationForm" class="coach-roster-form" hidden onsubmit="adaptCoachDecisionCycle(event)"><h5>Record adaptation for the saved cycle</h5><label for="coachAdaptationCommonCore">Common Core to preserve</label><input id="coachAdaptationCommonCore" maxlength="500" required placeholder="Principle that must remain unchanged"><label for="coachAdaptationBasis">Dynamic input / adaptation basis</label><input id="coachAdaptationBasis" maxlength="500" required placeholder="Current readiness or performance evidence"><label for="coachAdaptationChange">Individual adjustment</label><input id="coachAdaptationChange" maxlength="500" required placeholder="Specific adjustment"><button type="submit">Save adaptation</button></form></section>'+
   '<section id="coachDigitalTwinSection" hidden><h4>Digital Twin state (FEAT-042/043)</h4><p class="muted">Versioned state for this athlete, protected by verified Coach ownership and evidence references. Execution remains disabled.</p><form id="coachDigitalTwinForm" class="coach-roster-form" onsubmit="saveCoachDigitalTwinState(event)"><label for="coachTwinCaseId">Case reference</label><input id="coachTwinCaseId" maxlength="120" required placeholder="e.g. U15-CASE-001"><label for="coachTwinSourceEvent">Source event</label><input id="coachTwinSourceEvent" maxlength="120" required placeholder="e.g. RETEST_COMPLETED"><label for="coachTwinEvidenceRefs">Evidence references (comma-separated)</label><input id="coachTwinEvidenceRefs" maxlength="500" required placeholder="REF-001, REF-002"><label for="coachTwinState">State data (JSON)</label><textarea id="coachTwinState" rows="4" required>{\"readiness\":\"medium\",\"kpi\":{}}</textarea><button type="submit">Save Digital Twin state</button></form><div id="coachDigitalTwinNotice" class="notice">Select an athlete to load its scoped Digital Twin state.</div><pre id="coachDigitalTwinReadback" class="output"></pre><h5>State history</h5><div id="coachDigitalTwinHistory"></div></section>'+
   '<section id="athleteDecisionWorkspaceSection" hidden><h4>Decision-cycle workspace</h4><p class="muted">Read-only view of persisted assessments, attached evidence, diagnosis, Coach decisions, training and retest records.</p><div id="athleteDecisionWorkspaceNotice" class="notice">Loading persisted decision-cycle evidence…</div><div id="athleteDecisionWorkspaceContent"></div></section>'+
   '<section id="athleteActionHistorySection" hidden><h4>Coach action history</h4><p class="muted">Only tenant-scoped events attributable to this verified Coach are shown. FEAT-044 state links are related lineage; their actor is not verified.</p><div id="athleteActionHistoryNotice" class="notice">Loading recorded actions…</div><div id="athleteActionHistoryContent"></div></section>'+
   '<section id="athleteAuditReviewSection" hidden><h4>Coach-scoped audit review</h4><p class="muted">Search is restricted to this selected athlete and the verified Coach/tenant scope.</p><label for="coachAuditQuery">Search term</label><input id="coachAuditQuery" maxlength="200" placeholder="Enter an action, decision, or reason"><button type="button" onclick="loadCoachAthleteAuditReview()">Search verified audit</button><div id="athleteAuditReviewNotice" class="notice">Enter a search term to review this athlete’s verified audit events.</div><div id="athleteAuditReviewContent"></div></section>';
  loadCoachAthleteStatusHistory(athleteId);
  loadCoachAthleteDecisionCycles(athleteId);
  loadCoachDigitalTwinState(athleteId);
  loadCoachDecisionWorkspace(athleteId);
  loadCoachAssessmentData(athleteId);
  loadCoachProblemAnalysis(athleteId);
  loadCoachActionHistory(athleteId);
 }catch(e){
  if(selectedCoachAthleteId!==String(athleteId))return;
  if(detail)detail.textContent="Athlete details unavailable: "+String(e&&e.message?e.message:e);
  if(panel)panel.innerHTML='<p class="notice">Athlete details are unavailable outside the verified Coach scope.</p><button class="secondary" type="button" onclick="returnCoachRoster()">Back to my roster</button>';
 }
}
async function loadCoachDigitalTwinState(athleteId){
 const notice=document.getElementById("coachDigitalTwinNotice"),readback=document.getElementById("coachDigitalTwinReadback"),history=document.getElementById("coachDigitalTwinHistory");
 if(!notice||!readback||!history)return;
 notice.textContent="Loading Digital Twin state in verified Coach scope…";readback.textContent="";history.textContent="";
 try{const state=await stateCycleCall("/state-cycle/feat-042/digital-twin-state/"+encodeURIComponent(athleteId));
  if(selectedCoachAthleteId!==String(athleteId))return;readback.textContent=pretty(state);notice.textContent="Scoped Digital Twin state loaded · version "+state.version+". Execution remains disabled.";
 }catch(e){if(selectedCoachAthleteId!==String(athleteId))return;notice.textContent=String(e&&e.message?e.message:e).includes("404")?"No Digital Twin state recorded yet.":"Digital Twin read unavailable: "+String(e&&e.message?e.message:e)}
 try{const data=await stateCycleCall("/state-cycle/feat-043/state-history/"+encodeURIComponent(athleteId));
  if(selectedCoachAthleteId!==String(athleteId))return;const rows=Array.isArray(data.versions)?data.versions:[];
  history.innerHTML=rows.length?rows.map(x=>"<p><strong>Version "+escapeHtml(x.version)+"</strong> · "+escapeHtml(x.source_event||"")+" · "+escapeHtml(x.recorded_at||"")+"</p>").join(""):"<p class=\"muted\">No recorded state history.</p>";
 }catch(e){history.textContent="State history unavailable: "+String(e&&e.message?e.message:e)}
}

async function saveCoachDigitalTwinState(event){
 event.preventDefault();const athleteId=selectedCoachAthleteId,notice=document.getElementById("coachDigitalTwinNotice"),readback=document.getElementById("coachDigitalTwinReadback");
 if(!athleteId){notice.textContent="Select an athlete from your verified roster first.";return}
 let state;try{state=JSON.parse(document.getElementById("coachTwinState").value)}catch(_){notice.textContent="State data must be valid JSON.";return}
 if(!state||Array.isArray(state)||typeof state!=="object"||!Object.keys(state).length){notice.textContent="State data must be a non-empty JSON object.";return}
 const caseId=document.getElementById("coachTwinCaseId").value.trim(),sourceEvent=document.getElementById("coachTwinSourceEvent").value.trim(),evidenceRefs=document.getElementById("coachTwinEvidenceRefs").value.split(",").map(x=>x.trim()).filter(Boolean);
 if(!caseId||!sourceEvent||!evidenceRefs.length){notice.textContent="Case, source event, and at least one evidence reference are required.";return}
 notice.textContent="Saving versioned state with Coach ownership and audit…";
 try{const result=await stateCycleCall("/state-cycle/feat-042/digital-twin-state",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({entity_id:athleteId,state,source_event:sourceEvent,case_id:caseId,evidence_refs:evidenceRefs,coach_final_authority:true})});
  if(selectedCoachAthleteId!==String(athleteId))return;notice.textContent="Digital Twin state saved · version "+result.state.version+". Coach Final Authority retained; execution disabled.";readback.textContent=pretty(result);await loadCoachDigitalTwinState(athleteId);
 }catch(e){notice.textContent="Digital Twin state was not saved: "+String(e&&e.message?e.message:e)}
}
async function createCoachDecisionCycle(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId;
 const notice=document.getElementById("coachDecisionCycleNotice");
 const readback=document.getElementById("coachDecisionCycleReadback");
 const form=document.getElementById("coachDecisionCycleForm");
 if(!athleteId){notice.textContent="Select an athlete from your verified roster first.";return}
 const caseId=document.getElementById("coachDecisionCaseId").value.trim();
 const decision=document.getElementById("coachDecisionChoice").value.trim();
 const intervention=document.getElementById("coachIntervention").value.trim();
 const responseKpi=document.getElementById("coachResponseKpi").value.trim();
 const retest=document.getElementById("coachRetest").value.trim();
 if(!caseId||!decision||!intervention||!responseKpi||!retest){notice.textContent="Complete all decision-cycle fields.";return}
 notice.textContent="Saving decision cycle through the verified Coach API…";readback.textContent="";
 try{
  const result=await productCall("/decision",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
   athlete_id:athleteId,case_id:caseId,
   decision:{coach_choice:decision},intervention:{planned_action:intervention},
   response_kpi:{observation:responseKpi},retest:{observation:retest}
  })});
  currentCoachDecisionCycleId=result.decision_cycle_id;
  if(!currentCoachDecisionCycleId)throw new Error("Core did not return a durable decision_cycle_id.");
  const adaptationForm=document.getElementById("coachAdaptationForm");if(adaptationForm)adaptationForm.hidden=false;
  notice.textContent="Decision cycle saved. Durable ID: "+currentCoachDecisionCycleId;
  await loadCoachDecisionCycleReadback(athleteId,currentCoachDecisionCycleId);
 }catch(e){notice.textContent="Decision cycle was not saved: "+String(e&&e.message?e.message:e)}
}
async function loadCoachDecisionCycleReadback(athleteId,cycleId){
 const target=document.getElementById("coachDecisionCycleReadback");
 if(!target)return;
 try{
  const data=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/decision-cycles/"+encodeURIComponent(cycleId));
  if(selectedCoachAthleteId!==String(athleteId))return;
  target.textContent=pretty(data);
 }catch(e){target.textContent="Durable read-back unavailable: "+String(e&&e.message?e.message:e)}
}
async function adaptCoachDecisionCycle(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,notice=document.getElementById("coachDecisionCycleNotice");
 if(!athleteId||!currentCoachDecisionCycleId){notice.textContent="Create or load a durable decision cycle first.";return}
 const caseId=document.getElementById("coachDecisionCaseId").value.trim();
 const commonCore=document.getElementById("coachAdaptationCommonCore").value.trim();
 const basis=document.getElementById("coachAdaptationBasis").value.trim();
 const change=document.getElementById("coachAdaptationChange").value.trim();
 if(!caseId||!commonCore||!basis||!change){notice.textContent="Complete all adaptation fields.";return}
 notice.textContent="Saving adaptation against the exact durable decision cycle…";
 try{
  const result=await productCall("/adaptation",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
   athlete_id:athleteId,decision_cycle_id:currentCoachDecisionCycleId,
   case_id:caseId,operation:"individual_adaptation",
   common_core:{principle:commonCore},dynamic_inputs:{basis:basis},
   individual_change:{adjustment:change}
  })});
  notice.textContent="Adaptation saved. Cycle version: "+result.decision_cycle_version+".";
  await loadCoachDecisionCycleReadback(athleteId,currentCoachDecisionCycleId);
 }catch(e){notice.textContent="Adaptation was not saved: "+String(e&&e.message?e.message:e)}
}

async function changeCoachAthleteStatus(athleteId){
 const panel=document.getElementById("coachAthleteLifecycle"),status=document.getElementById("athleteNextStatus")?.value,reason=document.getElementById("athleteStatusReason")?.value.trim();
 if(!status||!reason){panel.insertAdjacentText("afterbegin","A status and reason are required. ");return}
 try{await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/status",{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status,reason})});await loadCoachRoster();await viewCoachAthlete(athleteId)}
 catch(e){panel.insertAdjacentText("afterbegin","Status change rejected: "+String(e&&e.message?e.message:e)+" ")}
}
function coachWorkspaceSection(title, rows, labelFields){
 const records=Array.isArray(rows)?rows:[];
 const cards=records.map(record=>{
  const label=labelFields.map(field=>record[field]).filter(value=>value!==null&&value!==undefined&&String(value)!=="").join(" · ")||"Recorded item";
  return '<article class="coach-workspace-record"><h5>'+escapeHtml(label)+'</h5><pre class="output">'+escapeHtml(pretty(record))+'</pre></article>';
 }).join("");
 return '<section class="coach-workspace-section"><h4>'+escapeHtml(title)+' ('+records.length+')</h4>'+
  (cards||'<p class="muted">No persisted '+escapeHtml(title.toLowerCase())+' records.</p>')+'</section>';
}
function renderCoachDecisionWorkspace(data){
 return [
  coachWorkspaceSection("Assessments and attached evidence",data.assessments,["template_id","assessed_at"]),
  coachWorkspaceSection("Baseline / current-state snapshots",data.state_snapshots,["snapshot_type","captured_at"]),
  coachWorkspaceSection("Problem statements",data.problem_statements,["statement","status"]),
  coachWorkspaceSection("Cause and context",data.cause_context_framings,["cause","framed_at"]),
  coachWorkspaceSection("Evidence-linked diagnoses",data.diagnoses,["diagnosis","resolution_state"]),
  coachWorkspaceSection("Decision candidates",data.decision_candidates,["title","status"]),
  coachWorkspaceSection("Decision rationales",data.decision_rationales,["rationale","recorded_at"]),
  coachWorkspaceSection("Alternative comparisons",data.decision_comparisons,["comparison_status","compared_at"]),
  coachWorkspaceSection("Coach reviews",data.coach_reviews,["action","status","reviewed_at"]),
  coachWorkspaceSection("Recorded decisions",data.decisions,["decision_summary","status","recorded_at"]),
  coachWorkspaceSection("Training plans",data.training_plans,["title","status"]),
  coachWorkspaceSection("Training sessions",data.training_sessions,["title","status"]),
  coachWorkspaceSection("Training / response / retest records",data.training_records,["feature_id","session_id","created_at"])
 ].join("");
}
async function loadCoachDecisionWorkspace(athleteId){
 const notice=document.getElementById("athleteDecisionWorkspaceNotice");
 const content=document.getElementById("athleteDecisionWorkspaceContent");
 if(!notice||!content)return;
 notice.textContent="Loading persisted assessment, evidence, decision, and training records…";
 content.innerHTML="";
 try{
  const data=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/decision-workspace");
  if(selectedCoachAthleteId!==String(athleteId))return;
  if(data.status==="INSUFFICIENT_EVIDENCE"||data.available===false){
   notice.textContent=data.message||"Insufficient durable evidence. Workspace data is unavailable.";return;
  }
  if(data.status==="NO_RECORDED_CYCLE"){
   notice.textContent=data.message||"No persisted decision-cycle records exist for this athlete.";return;
  }
  notice.textContent="Read-only workspace · persisted source records only · "+(data.missing_optional_tables||[]).length+" optional source table(s) unavailable.";
  content.innerHTML=renderCoachDecisionWorkspace(data);
 }catch(e){
  if(selectedCoachAthleteId!==String(athleteId))return;
  notice.textContent="Decision workspace unavailable: "+String(e&&e.message?e.message:e);
  content.textContent="No workspace data is displayed when authentication or authorization fails.";
 }
}


async function loadCoachAssessmentData(athleteId, preferredAssessmentId){
 const notice=document.getElementById("coachAssessmentNotice");
 const select=document.getElementById("coachAssessmentSelect");
 const list=document.getElementById("coachAssessmentList");
 if(!notice||!select||!list)return;
 notice.textContent="Loading persisted assessments in verified Coach scope…";
 list.textContent="";
 try{
  const data=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/assessments");
  if(selectedCoachAthleteId!==String(athleteId))return;
  const rows=Array.isArray(data.assessments)?data.assessments:[];
  const selected=preferredAssessmentId||currentCoachAssessmentId;
  select.innerHTML='<option value="">Select an assessment</option>'+rows.map(a=>'<option value="'+escapeHtml(a.assessment_id)+'">'+escapeHtml(a.template_id)+' · '+escapeHtml(a.assessed_at||a.created_at||"")+'</option>').join("");
  if(selected&&rows.some(a=>String(a.assessment_id)===String(selected))){
   select.value=selected;currentCoachAssessmentId=String(selected);
  }else{select.value="";currentCoachAssessmentId=null}
  list.innerHTML=rows.length?rows.map(a=>'<p class="muted"><strong>'+escapeHtml(a.template_id)+'</strong> · '+escapeHtml(a.assessment_id)+' · '+escapeHtml(a.assessed_at||"")+'</p>').join(""):'<p class="muted">No assessments have been recorded for this owned athlete yet.</p>';
  notice.textContent=rows.length+ " owned assessment(s) loaded. Select one before attaching evidence or creating a snapshot.";
 }catch(e){
  if(selectedCoachAthleteId!==String(athleteId))return;
  notice.textContent="Assessment data unavailable: "+String(e&&e.message?e.message:e);
  select.innerHTML='<option value="">Assessment data unavailable</option>';
  list.textContent="No assessment data is displayed when authentication or authorization fails.";
 }
}
function selectCoachAssessment(assessmentId){
 currentCoachAssessmentId=assessmentId||null;
 const notice=document.getElementById("coachAssessmentNotice");
 if(notice)notice.textContent=currentCoachAssessmentId?"Selected assessment "+currentCoachAssessmentId+". Server-side ownership is rechecked on every operation.":"Select an assessment before attaching evidence or creating a snapshot.";
}
async function createCoachAssessment(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,notice=document.getElementById("coachAssessmentNotice"),output=document.getElementById("coachAssessmentOutput");
 if(!athleteId){if(notice)notice.textContent="Select an athlete from your verified roster first.";return}
 let measurements;
 try{measurements=JSON.parse(document.getElementById("coachAssessmentMeasurements").value)}catch(_){notice.textContent="Measurements must be valid JSON.";return}
 if(!measurements||Array.isArray(measurements)||typeof measurements!=="object"||!Object.keys(measurements).length){notice.textContent="Measurements must be a non-empty JSON object.";return}
 const templateId=document.getElementById("coachAssessmentTemplateId").value.trim();
 if(!templateId){notice.textContent="Assessment template is required.";return}
 notice.textContent="Saving measurements through the verified Coach API…";output.textContent="";
 try{
  const created=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/assessments",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({template_id:templateId,measurements})});
  if(selectedCoachAthleteId!==String(athleteId))return;
  currentCoachAssessmentId=created.assessment_id;
  const readback=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/assessments/"+encodeURIComponent(created.assessment_id));
  if(selectedCoachAthleteId!==String(athleteId))return;
  output.textContent=pretty(readback);
  notice.textContent="Assessment saved and read back from the protected API. Actor and audit were derived server-side.";
  await loadCoachAssessmentData(athleteId,created.assessment_id);
  await loadCoachDecisionWorkspace(athleteId);
 }catch(e){notice.textContent="Assessment was not saved: "+String(e&&e.message?e.message:e)}
}
async function createCoachKpiDefinition(event){
 event.preventDefault();
 const notice=document.getElementById("coachAssessmentNotice"),output=document.getElementById("coachAssessmentOutput");
 if(!selectedCoachAthleteId){notice.textContent="Select an athlete from your verified roster first.";return}
 const kpiId=document.getElementById("coachKpiDefinitionId").value.trim();
 const name=document.getElementById("coachKpiDefinitionName").value.trim();
 const metricName=document.getElementById("coachKpiMetricName").value.trim();
 const unit=document.getElementById("coachKpiUnit").value.trim();
 const targetText=document.getElementById("coachKpiTarget").value.trim();
 const target=targetText?Number(targetText):null;
 if(!kpiId||!name||!metricName||!unit||(targetText&&!Number.isFinite(target))){notice.textContent="Complete KPI ID, name, metric, unit, and a valid optional target.";return}
 const direction=document.getElementById("coachKpiDirection").value;
 notice.textContent="Saving KPI definition in this verified Coach scope…";output.textContent="";
 try{
  const created=await productCall("/coach/kpi-definitions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kpi_id:kpiId,name,metric_name:metricName,unit,target,direction})});
  currentCoachKpiId=created.kpi_id;
  const captureInput=document.getElementById("coachKpiCaptureId");if(captureInput)captureInput.value=currentCoachKpiId;
  const readback=await productCall("/coach/kpi-definitions/"+encodeURIComponent(currentCoachKpiId));
  output.textContent=pretty(readback);
  notice.textContent="Coach-scoped KPI definition saved and read back. Other Coaches cannot read this definition.";
 }catch(e){notice.textContent="KPI definition was not saved: "+String(e&&e.message?e.message:e)}
}
async function createCoachKpiCapture(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,notice=document.getElementById("coachAssessmentNotice"),output=document.getElementById("coachAssessmentOutput");
 if(!athleteId||!currentCoachAssessmentId){notice.textContent="Select an owned athlete and an assessment first.";return}
 const kpiId=document.getElementById("coachKpiCaptureId").value.trim();
 const value=Number(document.getElementById("coachKpiCaptureValue").value);
 if(!kpiId||!Number.isFinite(value)){notice.textContent="Enter a Coach-scoped KPI ID and a finite numeric value.";return}
 notice.textContent="Saving KPI capture against the selected owned athlete and assessment…";output.textContent="";
 try{
  const created=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/kpi-captures",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kpi_id:kpiId,value,assessment_id:currentCoachAssessmentId})});
  if(selectedCoachAthleteId!==String(athleteId))return;
  currentCoachKpiCaptureId=created.capture_id;
  const ids=document.getElementById("coachKpiCaptureIds");if(ids)ids.value=currentCoachKpiCaptureId;
  const readback=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/kpi-captures/"+encodeURIComponent(currentCoachKpiCaptureId));
  output.textContent=pretty(readback);
  notice.textContent="KPI capture saved and read back under the current Coach ownership.";
 }catch(e){notice.textContent="KPI capture was not saved: "+String(e&&e.message?e.message:e)}
}
async function attachCoachAssessmentEvidence(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,notice=document.getElementById("coachAssessmentNotice"),output=document.getElementById("coachAssessmentOutput");
 if(!athleteId||!currentCoachAssessmentId){notice.textContent="Select an owned athlete and assessment first.";return}
 const evidenceId=document.getElementById("coachAssessmentEvidenceId").value.trim();
 if(!evidenceId){notice.textContent="An existing persisted evidence ID is required.";return}
 notice.textContent="Attaching evidence to the selected assessment…";output.textContent="";
 try{
  await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/assessments/"+encodeURIComponent(currentCoachAssessmentId)+"/evidence",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({evidence_id:evidenceId})});
  if(selectedCoachAthleteId!==String(athleteId))return;
  const readback=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/assessments/"+encodeURIComponent(currentCoachAssessmentId)+"/evidence");
  output.textContent=pretty(readback);
  notice.textContent="Evidence attachment saved and read back. The server verified that the evidence belongs to this assessment.";
  await loadCoachDecisionWorkspace(athleteId);
 }catch(e){notice.textContent="Evidence was not attached: "+String(e&&e.message?e.message:e)}
}
async function createCoachStateSnapshot(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,notice=document.getElementById("coachAssessmentNotice"),output=document.getElementById("coachAssessmentOutput");
 if(!athleteId||!currentCoachAssessmentId){notice.textContent="Select an owned athlete and assessment first.";return}
 const snapshotType=document.getElementById("coachSnapshotType").value;
 const captureIds=document.getElementById("coachKpiCaptureIds").value.split(",").map(x=>x.trim()).filter(Boolean);
 if(!captureIds.length){notice.textContent="At least one persisted KPI capture ID is required.";return}
 notice.textContent="Materializing the snapshot from the selected assessment and KPI captures…";output.textContent="";
 try{
  const created=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/state-snapshots",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({assessment_id:currentCoachAssessmentId,snapshot_type:snapshotType,kpi_capture_ids:captureIds})});
  if(selectedCoachAthleteId!==String(athleteId))return;
  const readback=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/state-snapshots/"+encodeURIComponent(created.snapshot_id));
  output.textContent=pretty(readback);
  notice.textContent="State snapshot saved and read back with assessment/KPI lineage and tenant audit.";
  await loadCoachDecisionWorkspace(athleteId);
 }catch(e){notice.textContent="State snapshot was not saved: "+String(e&&e.message?e.message:e)}
}

async function loadCoachActionHistory(athleteId){
 const notice=document.getElementById("athleteActionHistoryNotice");
 const content=document.getElementById("athleteActionHistoryContent");
 if(!notice||!content)return;
 notice.textContent="Loading tenant-scoped Coach actions…";
 content.innerHTML="";
 try{
  const data=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/action-history");
  if(selectedCoachAthleteId!==String(athleteId))return;
  if(data.status==="INSUFFICIENT_EVIDENCE"||data.available===false){
   notice.textContent=data.message||"Durable action history is unavailable.";return;
  }
  const items=Array.isArray(data.items)?data.items:[];
  if(data.status==="NO_RECORDED_ACTIONS"||!items.length){
   notice.textContent=data.message||"No attributable Coach actions are recorded for this athlete.";return;
  }
  notice.textContent=items.length+" recorded item(s). Reads do not create audit events.";
  content.innerHTML=items.map(item=>{
   const actor=item.actor_attribution_verified
    ? "Verified Coach actor: "+escapeHtml(item.actor_id||"")
    : "Related state link — actor attribution not verified";
   const detail=[item.decision_id?"Decision: "+item.decision_id:"",item.state_ref?"State: "+item.state_ref:"",item.state_version?"Version: "+item.state_version:""].filter(Boolean).join(" · ");
   return '<article class="coach-action-history-item"><h5>'+escapeHtml(item.action||"Recorded action")+'</h5><p>'+actor+'</p><small>'+escapeHtml(item.occurred_at||"Timestamp unavailable")+'</small><p>'+escapeHtml(item.reason||"")+'</p><p>'+escapeHtml(detail)+'</p><small>Source: '+escapeHtml(item.source||"")+'</small></article>';
  }).join("");
 }catch(e){
  if(selectedCoachAthleteId!==String(athleteId))return;
  notice.textContent="Action history unavailable: "+String(e&&e.message?e.message:e);
  content.textContent="No action data is displayed when authentication or authorization fails.";
 }
}

async function loadCoachAthleteAuditReview(){
 const athleteId=selectedCoachAthleteId;
 const notice=document.getElementById("athleteAuditReviewNotice");
 const content=document.getElementById("athleteAuditReviewContent");
 const query=(document.getElementById("coachAuditQuery")?.value||"").trim();
 if(!notice||!content)return;
 if(!athleteId){notice.textContent="Select an athlete from your verified roster first.";content.textContent="";return}
 if(!query){notice.textContent="Enter a search term. No audit query was sent.";content.textContent="";return}
 notice.textContent="Searching verified audit events for this owned athlete…";content.innerHTML="";
 try{
  const path="/coach/athletes/"+encodeURIComponent(athleteId)+"/audit-review?query="+encodeURIComponent(query);
  const data=await productCall(path);
  if(selectedCoachAthleteId!==String(athleteId))return;
  const rows=Array.isArray(data.results)?data.results:[];
  if(data.status==="INSUFFICIENT_EVIDENCE"){notice.textContent="Audit evidence is unavailable: "+String(data.message||"durable evidence is required");return}
  notice.textContent=rows.length?rows.length+" verified audit match(es). Read-only review; no audit event was created.":"No verified audit events match this search.";
  content.innerHTML=rows.map(item=>'<article class="coach-action-history-item"><h5>'+escapeHtml(item.action||"Recorded action")+'</h5><p>Verified Coach actor: '+escapeHtml(item.actor_id||"")+'</p><small>'+escapeHtml(item.occurred_at||"Timestamp unavailable")+'</small><p>'+escapeHtml(item.reason||"")+'</p><small>Source: '+escapeHtml(item.source||"")+' · '+escapeHtml(item.source_record_id||"")+'</small></article>').join("");
 }catch(e){
  if(selectedCoachAthleteId!==String(athleteId))return;
  notice.textContent="Audit review unavailable: "+String(e&&e.message?e.message:e);
  content.textContent="No audit data is displayed when authentication or authorization fails.";
 }
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
    <article class="coach-metric"><span class="muted">Decision records</span><strong>Read-only</strong><small>Review existing persisted cycles. New decisions and adaptations are written through the verified Coach-owned API; Digital Twin state uses the separately scoped state-cycle API.</small></article>
    <article class="coach-metric"><span class="muted">Scoped audit review</span><strong>Per athlete</strong><small>Select an owned athlete and use the Audit review tab to search verified Coach actions.</small></article>
  </div>
  <section id="coach-roster" class="coach-roster"><div class="coach-roster-head"><div><h3>My Athlete Roster</h3><p class="muted">Only athletes assigned to the authenticated coach in the authenticated tenant are shown.</p></div><button class="secondary" onclick="loadCoachRoster()">Refresh roster</button></div><form id="coachAthleteForm" class="coach-roster-form" onsubmit="createCoachAthlete(event)"><label for="newAthleteName">Athlete name</label><input id="newAthleteName" name="display_name" maxlength="120" required placeholder="Enter athlete name"><button type="submit">Add athlete to my roster</button></form><div class="coach-roster-form"><label for="athleteRosterSearch">Search my athletes</label><input id="athleteRosterSearch" type="search" maxlength="120" placeholder="Search by name or athlete ID" oninput="filterCoachRoster()"><button class="secondary" type="button" onclick="returnCoachRoster()">Back to roster</button></div><div id="coachRosterNotice" class="notice" role="status">Sign in with a verified Coach account to load your roster.</div><div id="coachRosterList" class="coach-roster-list"></div><pre id="coachAthleteDetail" class="output" aria-live="polite"></pre><div id="coachAthleteLifecycle" class="coach-roster" aria-live="polite"></div></section><section id="coach-groups" class="coach-roster"><div class="coach-roster-head"><div><h3>My Training Groups</h3><p class="muted">Groups and membership are restricted to your verified Coach and tenant scope.</p></div><button class="secondary" onclick="loadCoachGroups()">Refresh groups</button></div><form class="coach-roster-form" onsubmit="createCoachGroup(event)"><label for="newCoachGroupName">Group name</label><input id="newCoachGroupName" maxlength="100" required placeholder="e.g. U15 competition group"><button type="submit">Create group</button></form><div class="row"><label for="groupAthleteSelect">My athlete</label><select id="groupAthleteSelect"><option value="">Load your roster first</option></select></div><div id="coachGroupsNotice" class="notice" role="status">Sign in as Coach to load your groups.</div><div id="coachGroupsList"></div></section><section class="coach-legacy-actions notice" aria-live="polite">
  <h3>Protected Coach workflow boundary</h3>
  <p>Decision and adaptation are available in the protected Coach decision-cycle section above. Legacy unscoped Core routes remain retired. Digital Twin state read/write and version history are available in the selected athlete panel through the protected state-cycle API; no unscoped request is sent.</p>
</section>
<p class="notice coach-honesty">Athlete navigation uses the verified Coach roster and existing scoped profile, lifecycle, status-history, decision-history, workspace, action-history, and audit-review records. Coach remains the final authority.</p>
</div>` }

async function call(path,opts){const r=await fetch(API+path,opts||{});const j=await r.json();if(!r.ok)throw new Error(JSON.stringify(j));return j}
function escapeHtml(value){return String(value).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;")}
function pretty(x){return JSON.stringify(x,null,2)}
async function health(){try{const j=await call("/health");healthEl.textContent="CORE ONLINE";healthEl.style.background="#166534";return j}catch(e){healthEl.textContent="CORE UNREACHABLE";healthEl.style.background="#991b1b";return {error:String(e)}}}
const healthEl=document.getElementById("health");

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


async function loadCoachProblemAnalysis(athleteId, preferredProblemId){
 const notice=document.getElementById("coachProblemNotice"),select=document.getElementById("coachProblemSelect"),output=document.getElementById("coachProblemAnalysisOutput");
 if(!notice||!select||!output)return;
 notice.textContent="Loading problem statements in verified Coach scope…";output.textContent="";
 try{
  const data=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/problem-statements");
  if(selectedCoachAthleteId!==String(athleteId))return;
  const rows=Array.isArray(data.problem_statements)?data.problem_statements:[];
  const wanted=preferredProblemId||currentCoachProblemId;
  select.innerHTML='<option value="">Select a problem</option>'+rows.map(p=>'<option value="'+escapeHtml(p.problem_id)+'">'+escapeHtml(p.statement)+' · '+escapeHtml(p.problem_type)+'</option>').join("");
  if(wanted&&rows.some(p=>String(p.problem_id)===String(wanted))){select.value=wanted;currentCoachProblemId=String(wanted);await loadCoachProblemDetails(athleteId,currentCoachProblemId)}
  else{select.value="";currentCoachProblemId=null}
  notice.textContent=rows.length+" owned problem statement(s) loaded. Select one to review its cause and diagnosis.";
 }catch(e){notice.textContent="Problem analysis unavailable: "+String(e&&e.message?e.message:e);select.innerHTML='<option value="">Problem data unavailable</option>'}
}
function selectCoachProblem(problemId){
 currentCoachProblemId=problemId||null;
 if(currentCoachProblemId&&selectedCoachAthleteId)loadCoachProblemDetails(selectedCoachAthleteId,currentCoachProblemId);
}
async function loadCoachProblemDetails(athleteId,problemId){
 const output=document.getElementById("coachProblemAnalysisOutput"),notice=document.getElementById("coachProblemNotice");
 if(!output||!problemId)return;
 output.textContent="Loading cause/context and diagnosis read-back…";
 const root="/coach/athletes/"+encodeURIComponent(athleteId)+"/problem-statements/"+encodeURIComponent(problemId);
 try{
  const [cause,diagnoses]=await Promise.all([
   productCall(root+"/cause-context"),productCall(root+"/diagnoses")
  ]);
  if(selectedCoachAthleteId!==String(athleteId)||currentCoachProblemId!==String(problemId))return;
  const previousDiagnosisId=currentCoachDiagnosisId;
  currentCoachDiagnosisId=(diagnoses.diagnoses||[]).length?(diagnoses.diagnoses||[])[(diagnoses.diagnoses||[]).length-1].diagnosis_id:null;
  if(currentCoachDiagnosisId!==previousDiagnosisId)currentCoachCandidateId=null;
  output.textContent=pretty({cause_context:cause.framings||[],diagnoses:diagnoses.diagnoses||[]});
  if(currentCoachDiagnosisId)await loadCoachDecisionWorkflow(athleteId,currentCoachDiagnosisId);
  else{
   const candidateSelect=document.getElementById("coachCandidateSelect");
   if(candidateSelect)candidateSelect.innerHTML='<option value="">Create an evidence-linked diagnosis first</option>';
   const decisionOutput=document.getElementById("coachDecisionWorkflowOutput");
   if(decisionOutput)decisionOutput.textContent="";
   const decisionNotice=document.getElementById("coachDecisionNotice");
   if(decisionNotice)decisionNotice.textContent="No evidence-linked diagnosis is available. Decision candidates remain blocked.";
  }
  if(notice)notice.textContent="Scoped problem, cause/context, and diagnosis records loaded. Evidence references remain traceable.";
 }catch(e){output.textContent="Problem detail read-back unavailable: "+String(e&&e.message?e.message:e)}
}
async function createCoachProblemStatement(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,notice=document.getElementById("coachProblemNotice"),output=document.getElementById("coachProblemAnalysisOutput");
 if(!athleteId){notice.textContent="Select an athlete from your verified roster first.";return}
 if(!currentCoachAssessmentId){notice.textContent="Select an owned assessment in the Assessment & KPIs section first.";return}
 const statement=document.getElementById("coachProblemStatement").value.trim(),problemType=document.getElementById("coachProblemType").value.trim(),impact=document.getElementById("coachProblemImpact").value.trim();
 if(!statement||!problemType){notice.textContent="Problem statement and problem type are required.";return}
 notice.textContent="Saving structured problem statement through the protected Coach API…";output.textContent="";
 try{
  const record=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/problem-statements",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({assessment_id:currentCoachAssessmentId,statement,problem_type:problemType,impact:impact||null})});
  document.getElementById("coachProblemStatementForm").reset();
  currentCoachProblemId=record.problem_id;
  await loadCoachProblemAnalysis(athleteId,record.problem_id);
  notice.textContent="Problem statement saved and read back under the selected athlete and assessment.";
 }catch(e){notice.textContent="Problem statement was not saved: "+String(e&&e.message?e.message:e)}
}
async function createCoachCauseContext(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,problemId=currentCoachProblemId,notice=document.getElementById("coachProblemNotice"),output=document.getElementById("coachProblemAnalysisOutput");
 if(!athleteId||!problemId){notice.textContent="Select an owned problem statement first.";return}
 let context;try{context=JSON.parse(document.getElementById("coachProblemContext").value||"{}")}catch(_){notice.textContent="Context must be valid JSON.";return}
 if(!context||Array.isArray(context)||typeof context!=="object"){notice.textContent="Context must be a JSON object.";return}
 const cause=document.getElementById("coachProblemCause").value.trim(),factors=document.getElementById("coachProblemFactors").value.split(",").map(x=>x.trim()).filter(Boolean);
 if(!cause){notice.textContent="Cause is required.";return}
 notice.textContent="Saving cause/context with ownership and audit…";output.textContent="";
 try{
  const root="/coach/athletes/"+encodeURIComponent(athleteId)+"/problem-statements/"+encodeURIComponent(problemId);
  await productCall(root+"/cause-context",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({cause,context,contributing_factors:factors})});
  document.getElementById("coachCauseContextForm").reset();
  await loadCoachProblemDetails(athleteId,problemId);
 }catch(e){notice.textContent="Cause/context was not saved: "+String(e&&e.message?e.message:e)}
}
async function createCoachDiagnosis(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,problemId=currentCoachProblemId,notice=document.getElementById("coachProblemNotice"),output=document.getElementById("coachProblemAnalysisOutput");
 if(!athleteId||!problemId){notice.textContent="Select an owned problem statement first.";return}
 const diagnosis=document.getElementById("coachDiagnosisText").value.trim(),evidenceIds=document.getElementById("coachDiagnosisEvidenceIds").value.split(",").map(x=>x.trim()).filter(Boolean),confidence=document.getElementById("coachDiagnosisConfidence").value||null,resolutionState=document.getElementById("coachDiagnosisResolution").value;
 if(!diagnosis||!evidenceIds.length){notice.textContent="Diagnosis and at least one evidence ID are required.";return}
 notice.textContent="Verifying evidence and saving diagnosis…";output.textContent="";
 try{
  const root="/coach/athletes/"+encodeURIComponent(athleteId)+"/problem-statements/"+encodeURIComponent(problemId);
  await productCall(root+"/diagnoses",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({diagnosis,evidence_ids:evidenceIds,confidence,resolution_state:resolutionState})});
  document.getElementById("coachDiagnosisForm").reset();
  await loadCoachProblemDetails(athleteId,problemId);
  notice.textContent="Diagnosis saved. Only verified, non-E0 evidence linked to this athlete/problem/assessment is accepted.";
 }catch(e){notice.textContent="Diagnosis was not saved: "+String(e&&e.message?e.message:e)}
}


async function loadCoachDecisionWorkflow(athleteId,diagnosisId){
 const notice=document.getElementById("coachDecisionNotice"),select=document.getElementById("coachCandidateSelect"),output=document.getElementById("coachDecisionWorkflowOutput");
 if(!notice||!select||!output)return;
 notice.textContent="Loading decision candidates and Coach review history…";output.textContent="";
 try{
  const root="/coach/athletes/"+encodeURIComponent(athleteId)+"/diagnoses/"+encodeURIComponent(diagnosisId);
  const [candidateData,comparisonData]=await Promise.all([
   productCall(root+"/decision-candidates"),productCall(root+"/decision-comparisons")
  ]);
  if(selectedCoachAthleteId!==String(athleteId)||currentCoachDiagnosisId!==String(diagnosisId))return;
  const rows=Array.isArray(candidateData.candidates)?candidateData.candidates:[];
  const options=rows.map(x=>'<option value="'+escapeHtml(x.candidate_id)+'">'+escapeHtml(x.candidate_type)+" · "+escapeHtml(x.status)+'</option>').join("");
  select.innerHTML='<option value="">Select a candidate</option>'+options;
  ["coachCompareCandidateA","coachCompareCandidateB"].forEach(id=>{
   const el=document.getElementById(id);if(el)el.innerHTML='<option value="">Select candidate</option>'+options;
  });
  const wanted=currentCoachCandidateId;
  if(wanted&&rows.some(x=>String(x.candidate_id)===String(wanted)))select.value=wanted;
  else if(rows.length){currentCoachCandidateId=rows[0].candidate_id;select.value=currentCoachCandidateId}
  else currentCoachCandidateId=null;
  const details=currentCoachCandidateId?await loadCoachCandidateDetails(athleteId,currentCoachCandidateId):null;
  output.textContent=pretty({candidates:rows,comparisons:comparisonData.comparisons||[],selected_candidate_details:details});
  if(currentCoachDecisionId)await loadCoachTrainingWorkflow(athleteId,currentCoachDecisionId);
  notice.textContent=rows.length+" candidate(s) loaded. Each requires explicit Coach review before a decision can be recorded.";
 }catch(e){notice.textContent="Decision workflow unavailable: "+String(e&&e.message?e.message:e)}
}
function selectCoachCandidate(candidateId){
 currentCoachCandidateId=candidateId||null;
 if(currentCoachCandidateId&&selectedCoachAthleteId)loadCoachCandidateDetails(selectedCoachAthleteId,currentCoachCandidateId).then(data=>{
  const output=document.getElementById("coachDecisionWorkflowOutput");if(output&&data)output.textContent=pretty(data);
 });
}
async function loadCoachCandidateDetails(athleteId,candidateId){
 const root="/coach/athletes/"+encodeURIComponent(athleteId)+"/decision-candidates/"+encodeURIComponent(candidateId);
 const [rationales,reviews,decisions]=await Promise.all([
  productCall(root+"/rationales"),productCall(root+"/coach-review"),productCall(root+"/decision-record")
 ]);
 const decisionRows=decisions.decisions||[];
 currentCoachDecisionId=decisionRows.length?decisionRows[decisionRows.length-1].decision_id:null;
 return {rationales:rationales.rationales||[],reviews:reviews.reviews||[],decisions:decisionRows};
}
async function generateCoachDecisionCandidates(){
 const athleteId=selectedCoachAthleteId,diagnosisId=currentCoachDiagnosisId,notice=document.getElementById("coachDecisionNotice");
 if(!athleteId||!diagnosisId){notice.textContent="Select a problem with an evidence-linked diagnosis first.";return}
 notice.textContent="Revalidating evidence and generating reviewable options…";
 try{
  const path="/coach/athletes/"+encodeURIComponent(athleteId)+"/diagnoses/"+encodeURIComponent(diagnosisId)+"/decision-candidates";
  const result=await productCall(path,{method:"POST"});
  currentCoachCandidateId=(result.candidates||[])[0]?.candidate_id||null;
  await loadCoachDecisionWorkflow(athleteId,diagnosisId);
  notice.textContent=(result.candidates||[]).length+" candidate option(s) available for explicit Coach review.";
 }catch(e){notice.textContent="Candidate generation blocked: "+String(e&&e.message?e.message:e)}
}
async function recordCoachDecisionRationale(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,candidateId=currentCoachCandidateId,notice=document.getElementById("coachDecisionNotice");
 if(!athleteId||!candidateId){notice.textContent="Select a decision candidate first.";return}
 const rationale=document.getElementById("coachDecisionRationale").value.trim(),evidenceIds=document.getElementById("coachDecisionRationaleEvidence").value.split(",").map(x=>x.trim()).filter(Boolean);
 if(!rationale||!evidenceIds.length){notice.textContent="Rationale and verified evidence IDs are required.";return}
 try{
  const path="/coach/athletes/"+encodeURIComponent(athleteId)+"/decision-candidates/"+encodeURIComponent(candidateId)+"/rationales";
  await productCall(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({rationale,evidence_ids:evidenceIds})});
  document.getElementById("coachDecisionRationaleForm").reset();
  const data=await loadCoachCandidateDetails(athleteId,candidateId);document.getElementById("coachDecisionWorkflowOutput").textContent=pretty(data);
  notice.textContent="Evidence-linked rationale saved. Coach review is still required.";
 }catch(e){notice.textContent="Rationale was not saved: "+String(e&&e.message?e.message:e)}
}
async function compareCoachDecisionCandidates(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,diagnosisId=currentCoachDiagnosisId,notice=document.getElementById("coachDecisionNotice");
 const a=document.getElementById("coachCompareCandidateA").value,b=document.getElementById("coachCompareCandidateB").value;
 if(!athleteId||!diagnosisId||!a||!b||a===b){notice.textContent="Select two distinct candidates from this diagnosis.";return}
 try{
  const path="/coach/athletes/"+encodeURIComponent(athleteId)+"/diagnoses/"+encodeURIComponent(diagnosisId)+"/decision-comparisons";
  await productCall(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({candidate_ids:[a,b]})});
  await loadCoachDecisionWorkflow(athleteId,diagnosisId);notice.textContent="Alternatives compared and submitted for Coach review.";
 }catch(e){notice.textContent="Comparison was not saved: "+String(e&&e.message?e.message:e)}
}
async function reviewCoachDecisionCandidate(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,candidateId=currentCoachCandidateId,notice=document.getElementById("coachDecisionNotice");
 if(!athleteId||!candidateId){notice.textContent="Select a decision candidate first.";return}
 const action=document.getElementById("coachDecisionReviewAction").value,overrideReason=document.getElementById("coachDecisionOverrideReason").value.trim();
 if(action==="OVERRIDE"&&!overrideReason){notice.textContent="An override reason is required.";return}
 try{
  const path="/coach/athletes/"+encodeURIComponent(athleteId)+"/decision-candidates/"+encodeURIComponent(candidateId)+"/coach-review";
  await productCall(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action,override_reason:overrideReason||null})});
  const data=await loadCoachCandidateDetails(athleteId,candidateId);document.getElementById("coachDecisionWorkflowOutput").textContent=pretty(data);
  notice.textContent="Coach review recorded from the authenticated Coach identity. Execution remains disabled.";
 }catch(e){notice.textContent="Coach review was not saved: "+String(e&&e.message?e.message:e)}
}
async function recordCoachDecision(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,candidateId=currentCoachCandidateId,notice=document.getElementById("coachDecisionNotice");
 if(!athleteId||!candidateId){notice.textContent="Select a decision candidate first.";return}
 const outcomeIntent=document.getElementById("coachDecisionOutcomeIntent").value.trim(),decisionSummary=document.getElementById("coachDecisionSummary").value.trim();
 if(!outcomeIntent){notice.textContent="Outcome intent is required.";return}
 try{
  const path="/coach/athletes/"+encodeURIComponent(athleteId)+"/decision-candidates/"+encodeURIComponent(candidateId)+"/decision-record";
  await productCall(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({outcome_intent:outcomeIntent,decision_summary:decisionSummary||null})});
  const data=await loadCoachCandidateDetails(athleteId,candidateId);document.getElementById("coachDecisionWorkflowOutput").textContent=pretty(data);
  if(currentCoachDecisionId)await loadCoachTrainingWorkflow(athleteId,currentCoachDecisionId);
  notice.textContent="Decision recorded after explicit Coach review. No training execution was authorized.";
 }catch(e){notice.textContent="Decision was not recorded: "+String(e&&e.message?e.message:e)}
}


async function loadCoachTrainingWorkflow(athleteId,decisionId){
 const notice=document.getElementById("coachTrainingNotice"),planSelect=document.getElementById("coachTrainingPlanSelect"),output=document.getElementById("coachTrainingWorkflowOutput");
 if(!notice||!planSelect||!output)return;
 if(!decisionId){notice.textContent="A recorded Coach decision is required before creating a training plan.";return}
 notice.textContent="Loading draft training plans and sessions…";
 try{
  const data=await productCall("/coach/athletes/"+encodeURIComponent(athleteId)+"/training-plans");
  if(selectedCoachAthleteId!==String(athleteId)||currentCoachDecisionId!==String(decisionId))return;
  const plans=data.training_plans||[];
  const options=plans.map(p=>'<option value="'+escapeHtml(p.plan_id)+'">'+escapeHtml(p.title)+' · '+escapeHtml(p.status)+'</option>').join("");
  planSelect.innerHTML='<option value="">Select a draft plan</option>'+options;
  if(currentCoachPlanId&&plans.some(p=>String(p.plan_id)===String(currentCoachPlanId)))planSelect.value=currentCoachPlanId;
  else if(plans.length){currentCoachPlanId=plans[0].plan_id;planSelect.value=currentCoachPlanId}
  else currentCoachPlanId=null;
  if(currentCoachPlanId)await loadCoachTrainingSessions(athleteId,currentCoachPlanId);
  else{const sessionSelect=document.getElementById("coachTrainingSessionSelect");if(sessionSelect)sessionSelect.innerHTML='<option value="">Create a draft session first</option>';output.textContent=pretty({training_plans:plans})}
  notice.textContent=plans.length+" draft training plan(s) loaded. No plan or session is executed automatically.";
 }catch(e){notice.textContent="Training plan read-back unavailable: "+String(e&&e.message?e.message:e)}
}
async function loadCoachTrainingSessions(athleteId,planId){
 const output=document.getElementById("coachTrainingWorkflowOutput"),select=document.getElementById("coachTrainingSessionSelect");
 if(!output||!select)return;
 const path="/coach/athletes/"+encodeURIComponent(athleteId)+"/training-plans/"+encodeURIComponent(planId)+"/sessions";
 try{
  const data=await productCall(path),rows=data.sessions||[];
  const options=rows.map(x=>'<option value="'+escapeHtml(x.session_id)+'">'+escapeHtml(x.title)+' · '+escapeHtml(x.duration_minutes)+' min</option>').join("");
  select.innerHTML='<option value="">Select a session</option>'+options;
  if(currentCoachSessionId&&rows.some(x=>String(x.session_id)===String(currentCoachSessionId)))select.value=currentCoachSessionId;
  else if(rows.length){currentCoachSessionId=rows[0].session_id;select.value=currentCoachSessionId}
  else currentCoachSessionId=null;
  if(currentCoachSessionId)await loadCoachTrainingDosages(athleteId,currentCoachSessionId);
  output.textContent=pretty({training_sessions:rows});
 }catch(e){output.textContent="Session read-back unavailable: "+String(e&&e.message?e.message:e)}
}
async function loadCoachTrainingDosages(athleteId,sessionId){
 const output=document.getElementById("coachTrainingWorkflowOutput");
 if(!output)return;
 try{
  const path="/coach/athletes/"+encodeURIComponent(athleteId)+"/training-sessions/"+encodeURIComponent(sessionId)+"/dosage";
  const data=await productCall(path);
  output.textContent=pretty({session_id:sessionId,dosages:data.dosages||[]});
 }catch(e){output.textContent="Dosage read-back unavailable: "+String(e&&e.message?e.message:e)}
}
function selectCoachTrainingPlan(planId){
 currentCoachPlanId=planId||null;currentCoachSessionId=null;
 if(currentCoachPlanId&&selectedCoachAthleteId)loadCoachTrainingSessions(selectedCoachAthleteId,currentCoachPlanId);
}
function selectCoachTrainingSession(sessionId){
 currentCoachSessionId=sessionId||null;
 if(currentCoachSessionId&&selectedCoachAthleteId)loadCoachTrainingDosages(selectedCoachAthleteId,currentCoachSessionId);
}
async function createCoachTrainingPlan(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,decisionId=currentCoachDecisionId,notice=document.getElementById("coachTrainingNotice");
 if(!athleteId||!decisionId){notice.textContent="Record an explicit Coach decision before creating a plan.";return}
 let constraints;try{constraints=JSON.parse(document.getElementById("coachTrainingPlanConstraints").value||"{}")}catch(_){notice.textContent="Constraints must be valid JSON.";return}
 if(!constraints||Array.isArray(constraints)||typeof constraints!=="object"){notice.textContent="Constraints must be a JSON object.";return}
 const title=document.getElementById("coachTrainingPlanTitle").value.trim(),objective=document.getElementById("coachTrainingPlanObjective").value.trim();
 try{
  const path="/coach/athletes/"+encodeURIComponent(athleteId)+"/training-plans";
  const plan=await productCall(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision_id:decisionId,title,objective,constraints})});
  currentCoachPlanId=plan.plan_id;document.getElementById("coachTrainingPlanForm").reset();
  await loadCoachTrainingWorkflow(athleteId,decisionId);notice.textContent="Draft training plan saved from the Coach-reviewed decision. Execution remains disabled.";
 }catch(e){notice.textContent="Training plan was not saved: "+String(e&&e.message?e.message:e)}
}
async function createCoachTrainingSession(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,planId=currentCoachPlanId,notice=document.getElementById("coachTrainingNotice");
 if(!athleteId||!planId){notice.textContent="Select an owned draft training plan first.";return}
 let blocks;try{blocks=JSON.parse(document.getElementById("coachTrainingSessionBlocks").value)}catch(_){notice.textContent="Session blocks must be a valid JSON array.";return}
 if(!Array.isArray(blocks)||!blocks.length){notice.textContent="At least one session block is required.";return}
 const title=document.getElementById("coachTrainingSessionTitle").value.trim(),duration=Number(document.getElementById("coachTrainingSessionDuration").value);
 try{
  const path="/coach/athletes/"+encodeURIComponent(athleteId)+"/training-plans/"+encodeURIComponent(planId)+"/sessions";
  const session=await productCall(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title,duration_minutes:duration,blocks})});
  currentCoachSessionId=session.session_id;document.getElementById("coachTrainingSessionForm").reset();
  await loadCoachTrainingSessions(athleteId,planId);notice.textContent="Draft session saved. Block durations must total the session duration.";
 }catch(e){notice.textContent="Training session was not saved: "+String(e&&e.message?e.message:e)}
}
async function createCoachTrainingDosage(event){
 event.preventDefault();
 const athleteId=selectedCoachAthleteId,sessionId=currentCoachSessionId,notice=document.getElementById("coachTrainingNotice");
 if(!athleteId||!sessionId){notice.textContent="Select an owned draft session first.";return}
 const blockName=document.getElementById("coachTrainingDosageBlock").value.trim(),sets=Number(document.getElementById("coachTrainingDosageSets").value),reps=Number(document.getElementById("coachTrainingDosageReps").value),rest=Number(document.getElementById("coachTrainingDosageRest").value||0),notes=document.getElementById("coachTrainingDosageNotes").value.trim();
 try{
  const path="/coach/athletes/"+encodeURIComponent(athleteId)+"/training-sessions/"+encodeURIComponent(sessionId)+"/dosage";
  await productCall(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({block_name:blockName,sets,reps,rest_seconds:rest,dosage_notes:notes||null})});
  document.getElementById("coachTrainingDosageForm").reset();await loadCoachTrainingDosages(athleteId,sessionId);
  notice.textContent="Draft dosage saved for the selected session block. No execution was triggered.";
 }catch(e){notice.textContent="Dosage was not saved: "+String(e&&e.message?e.message:e)}
}


async function loadCoachProblemLibrary(){
 const notice=document.getElementById("coachProblemLibraryNotice"),select=document.getElementById("coachProblemLibrarySelect"),output=document.getElementById("coachProblemLibraryOutput");
 if(!notice||!select||!output)return;
 notice.textContent="Loading only APPROVED, VERIFIED problem entries with complete provenance…";
 try{
  const data=await productCall("/coach/problem-library");
  const rows=data.items||[];
  select.innerHTML='<option value="">Select an approved problem entry</option>'+rows.map(x=>'<option value="'+escapeHtml(x.knowledge_id)+'">'+escapeHtml(x.title)+' · '+escapeHtml(x.knowledge_id)+'</option>').join("");
  output.textContent=pretty({publication_gate:data.publication_gate,items:rows});
  notice.textContent=rows.length+" provenance-verified problem entry/entries available.";
 }catch(e){notice.textContent="Problem library unavailable: "+String(e&&e.message?e.message:e);select.innerHTML='<option value="">No approved problem entries available</option>'}
}
function selectCoachProblemLibraryItem(itemId){
 currentCoachLibraryItemId=itemId||null;
}
async function createCoachProblemLibrarySelection(){
 const athleteId=selectedCoachAthleteId,assessmentId=currentCoachAssessmentId,libraryItemId=currentCoachLibraryItemId,notice=document.getElementById("coachProblemLibraryNotice");
 if(!athleteId||!assessmentId){notice.textContent="Select an athlete and an owned assessment first.";return}
 if(!libraryItemId){notice.textContent="Select an approved problem library entry first.";return}
 try{
  const path="/coach/athletes/"+encodeURIComponent(athleteId)+"/assessments/"+encodeURIComponent(assessmentId)+"/problem-library-selections";
  const record=await productCall(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({library_item_id:libraryItemId})});
  notice.textContent="Problem library entry attached to the selected owned assessment. Selection is audit logged.";
  await loadCoachProblemLibrarySelections();
 }catch(e){notice.textContent="Problem selection was not saved: "+String(e&&e.message?e.message:e)}
}
async function loadCoachProblemLibrarySelections(){
 const athleteId=selectedCoachAthleteId,assessmentId=currentCoachAssessmentId,notice=document.getElementById("coachProblemLibraryNotice"),output=document.getElementById("coachProblemLibraryOutput");
 if(!athleteId||!assessmentId){notice.textContent="Select an athlete and assessment before reading problem selections.";return}
 try{
  const path="/coach/athletes/"+encodeURIComponent(athleteId)+"/assessments/"+encodeURIComponent(assessmentId)+"/problem-library-selections";
  const data=await productCall(path);
  output.textContent=pretty({assessment_id:assessmentId,selections:data.selections||[]});
  notice.textContent=(data.selections||[]).length+" problem library selection(s) read back for this assessment.";
 }catch(e){notice.textContent="Problem library selections unavailable: "+String(e&&e.message?e.message:e)}
}
