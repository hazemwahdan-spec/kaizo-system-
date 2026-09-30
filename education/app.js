const modules=[
{id:"E01",title:"Observation Before Intervention",desc:"Practice separating observation, interpretation, and action.",source:"KAIZO governed demo content"},
{id:"E02",title:"Decision Cycle Practice",desc:"Decision → intervention → KPI → retest → audit.",source:"KAIZO methodology boundary"},
{id:"E03",title:"Pressure & Transfer",desc:"Turn learning into controlled practice and transfer.",source:"Coach practice prompt"}
];
const state=JSON.parse(localStorage.getItem("kaizo_p11_education")||"{}");
const el=document.getElementById("modules");
el.innerHTML=modules.map(m=>"<article class='module'><h3>"+m.id+" · "+m.title+"</h3><p>"+m.desc+"</p><div class='meta'>Source: "+m.source+" · Evidence status: EDUCATIONAL DEMO</div><button data-id='"+m.id+"'>"+(state[m.id]?"Completed locally":"Mark practiced")+"</button></article>").join("");
document.querySelectorAll("[data-id]").forEach(b=>b.onclick=()=>{state[b.dataset.id]=true;localStorage.setItem("kaizo_p11_education",JSON.stringify(state));b.textContent="Completed locally";renderRecord()});
function renderRecord(){document.getElementById("record").textContent="Modules practiced locally: "+Object.keys(state).filter(k=>state[k]).join(", ")||"No modules practiced yet."}
document.getElementById("saveReflection").onclick=()=>{localStorage.setItem("kaizo_p11_reflection",JSON.stringify({practice:document.getElementById("practice").value,reflection:document.getElementById("reflection").value,at:new Date().toISOString(),authoritative:false}));document.getElementById("saved").textContent="Reflection saved locally — NON-AUTHORITATIVE.";renderRecord()};
renderRecord();