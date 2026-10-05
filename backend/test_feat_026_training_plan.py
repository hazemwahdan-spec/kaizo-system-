import os,uuid
os.environ['KAIZO_PERSISTENCE_MODE']='postgres'
os.environ['DATABASE_URL']='postgresql://postgres:postgres@localhost:5432/kaizo_test'
from fastapi.testclient import TestClient
import main,persistence
persistence.initialize(); client=TestClient(main.app)
def post(p,x):
 r=client.post(p,json=x); assert r.status_code in (200,201),(r.status_code,r.text); return r.json()
def build_decision():
 s=uuid.uuid4().hex[:8]; a=post('/api/v1/athletes',{'display_name':'FEAT026 '+s}); ass=post('/api/v1/assessments',{'athlete_id':a['athlete_id'],'template_id':'FEAT-026','measurements':{'score':5},'recorded_by':'coach-feat026'}); p=post('/api/v1/problem-statements',{'athlete_id':a['athlete_id'],'assessment_id':ass['assessment_id'],'statement':'Training plan test','problem_type':'TECHNICAL','created_by':'coach-feat026'}); e=post('/api/v1/evidence',{'evidence_id':'FEAT026-'+s,'subject_type':'problem','subject_id':p['problem_id'],'evidence_level':'E2','status':'VERIFIED','source_ref':'TEST','claim':'Evidence','observed_value':{'score':5},'verified_by':'coach-feat026'}); d=post('/api/v1/problem-statements/'+p['problem_id']+'/diagnosis',{'problem_id':p['problem_id'],'evidence_ids':[e['evidence_id']],'diagnosis':'Test diagnosis','diagnosed_by':'coach-feat026'}); c=post('/api/v1/diagnoses/'+d['diagnosis_id']+'/decision-candidates',{'diagnosis_id':d['diagnosis_id'],'requested_by':'coach-feat026'})['candidates'][0]; post('/api/v1/decision-candidates/'+c['candidate_id']+'/coach-review',{'candidate_id':c['candidate_id'],'action':'CONFIRM','coach_id':'coach-feat026'}); return post('/api/v1/decision-candidates/'+c['candidate_id']+'/decision-record',{'candidate_id':c['candidate_id'],'coach_id':'coach-feat026','outcome_intent':'Improve execution'}) ,a
def test_plan():
 d,a=build_decision(); r=post('/api/v1/training-plans',{'athlete_id':a['athlete_id'],'decision_id':d['decision_id'],'title':'Initial plan','objective':'Improve execution quality','created_by':'coach-feat026','constraints':{'duration_min':60}}); assert r['status']=='DRAFT' and r['coach_final_authority'] and not r['execution_authorized']; q=client.get('/api/v1/training-plans/'+r['plan_id']); assert q.status_code==200 and q.json()['plan_id']==r['plan_id']
if __name__=='__main__': test_plan(); print('FEAT-026 acceptance tests passed')