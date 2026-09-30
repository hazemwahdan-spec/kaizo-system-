const records=[];
const $=id=>document.getElementById(id);
function addRecord(type,source,details){records.push({type,source,details,at:new Date().toISOString()});render();localStorage.setItem("kaizo_p10_competition_records",JSON.stringify(records));}
function render(){const el=$("register");el.innerHTML=records.length?records.map(r=>"<div class='record'><strong>"+r.type+"</strong><span class='source'>Source: "+r.source+" · "+r.at+"</span><div>"+r.details+"</div></div>").join(""):"<p class='muted'>No records yet.</p>"}
$("saveCompetition").onclick=()=>{addRecord("Competition case","Competition metadata",$("competition").value+" · "+$("date").value+" · "+$("venue").value+" · "+$("phase").value);$("competitionStatus").textContent="Competition case recorded locally — DEMO / NON-AUTHORITATIVE."};
$("saveParticipation").onclick=()=>addRecord("Athlete participation","Coach-entered participation",$("athlete").value+" · "+$("category").value+" · "+$("division").value+" · "+$("participation").value);
$("saveBout").onclick=()=>addRecord("Bout / match",$("source").value,$("round").value+" vs "+$("opponent").value+" · "+$("outcome").value+" · "+$("detail").value+" · "+$("timestamp").value);
$("saveObservation").onclick=()=>addRecord("Coach observation","Coach-entered observation",$("observation").value+" Follow-up: "+$("followup").value);
try{const saved=JSON.parse(localStorage.getItem("kaizo_p10_competition_records")||"[]");saved.forEach(r=>records.push(r));}catch(e){}
render();