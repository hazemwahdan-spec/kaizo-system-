import os, uuid
os.environ['KAIZO_PERSISTENCE_MODE']='postgres'
os.environ['DATABASE_URL']='postgresql://postgres:postgres@localhost:5432/kaizo_test'
from fastapi.testclient import TestClient
import main, persistence
persistence.initialize(); client=TestClient(main.app)
def post(p,x):
 r=client.post(p,json=x); assert r.status_code in (200,201),(r.status_code,r.text); return r.json()
def candidate():
 s=uuid.uuid4().hex[:8]; a=post('/api/v1/athletes',{'display_name':'FEAT025 '+s}); ass=post('/api/v1/assessments',{'athlete_id':a['athlete_id'],'template_id':'FEAT-025','measurements':{'score':5},'recorded_by':'coach-feat025'}); p=post('/api/v1/problem-statements',{'athlete_id':a['athlete_id'],'assessment_id':ass['assessment_id'],'statement':'Decision record test','problem_type':'TECHNICAL','created_by':'coach-feat025'}); e=post('/api/v1/evidence',{'evidence_id':'FEAT025-'+s,'subject_type':'problem','subject_id':p['problem_id'],'evidence_level':'E2','status':'VERIFIED','source_ref':'TEST','claim':'Evidence','observed_value':{'score':5},'verified_by':'coach-feat025'}); d=post('/api/v1/problem-statements/'+p['problem_id']+'/diagnosis',{'problem_id':p['problem_id'],'evidence_ids':[e['evidence_id']],'diagnosis':'Test diagnosis','diagnosed_by':'coach-feat025'}); return post('/api/v1/diagnoses/'+d['diagnosis_id']+'/decision-candidates',{'diagnosis_id':d['diagnosis_id'],'requested_by':'coach-feat025'})['candidates'][0]
def test_requires_review():
 c=candidate(); r=client.post('/api/v1/decision-candidates/'+c['candidate_id']+'/decision-record',json={'candidate_id':c['candidate_id'],'coach_id':'coach-feat025','outcome_intent':'Improve outcome'}); assert r.status_code==409
def test_record_readback():
 c=candidate(); post('/api/v1/decision-candidates/'+c['candidate_id']+'/coach-review',{'candidate_id':c['candidate_id'],'action':'CONFIRM','coach_id':'coach-feat025'}); r=post('/api/v1/decision-candidates/'+c['candidate_id']+'/decision-record',{'candidate_id':c['candidate_id'],'coach_id':'coach-feat025','outcome_intent':'Improve execution quality'}); assert r['status']=='RECORDED' and r['coach_action']=='CONFIRM' and r['coach_final_authority'] and not r['execution_authorized']; q=client.get('/api/v1/decision-candidates/'+c['candidate_id']+'/decision-record'); assert q.status_code==200 and q.json()['records']
if __name__=='__main__': test_requires_review(); test_record_readback(); print('FEAT-025 acceptance tests passed')