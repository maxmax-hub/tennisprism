"""Portable Skill behavior; synthetic fixtures never leave the test workspace."""
import copy
import importlib
import json
from pathlib import Path
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

SKILL=Path(__file__).resolve().parents[1]/'skills/tennisprism'
sys.path.insert(0,str(SKILL/'scripts'))
from tennis_runtime import main,reporting
from tennis_runtime.h5 import build

def report(manifest):
    e={'frame_id':manifest['frames'][0]['id'],'timestamp':.5,'description':'Synthetic test frame'}
    return {'schema_version':'3.0','evidence_id':manifest['evidence_id'],'summary':'NTRP 3.5 接口测试数据','player':{'description':'Synthetic near player'},'assessment':{'rating_system':'NTRP','rating':3.5,'rating_status':'video_estimate','label':'接口测试值','confidence':'low','basis':'Synthetic fixture, no real rating','not_observed':['Test only']},'strengths':[],'priorities':[{'kind':'potential','alternative':'来球差异','title':'测试潜在问题','observation':'Synthetic movement','interpretation':'Synthetic hypothesis','confidence':'low','evidence':[e],'drill':{'title':'测试对照','setup':'同条件喂球','duration':'5 分钟','steps':['A 组','B 组'],'cue':'比较结果','success_criterion':'比较同一目标区回球','supports':'B 更稳定时复测','against':'无优势时保留原动作','easier':'降低速度','harder':'增加方向变化','source_kind':'authored','sources':[],'adaptation':'Synthetic authored test, not a prescription'}}],'limitations':['Test only'],'next_session_focus':['Test only']}

@pytest.fixture
def server(monkeypatch):
    root=Path(__file__).resolve().parents[1]/'work/skill-tests'/uuid.uuid4().hex
    def preview(source,out,progress):
        out.mkdir(parents=True);(out/'preview.mp4').write_bytes(b'fixture');(out/'thumbnail.jpg').write_bytes(b'fixture')
        return {'duration':10,'width':640,'height':360,'fps':30,'has_audio':False,'codec':'fixture'}
    def evidence(source,out,**kwargs):
        out.mkdir(parents=True);(out/'frame.jpg').write_bytes(b'fixture')
        m={'evidence_id':uuid.uuid4().hex,'video':{'duration':10},'window':{'start':0,'end':10},'sampling':{},'frames':[{'id':uuid.uuid4().hex,'timestamp':.5,'file':'frame.jpg','group':'sequence_1'}],'sheets':[]}
        (out/'manifest.json').write_text(json.dumps(m));return m
    monkeypatch.setattr(main.media,'prepare_video',preview);monkeypatch.setattr(main.media,'prepare_evidence',evidence)
    app=main.create_app(root)
    # Keep the API request observable, but resolve work deterministically.
    app.state.executor.shutdown()
    class Immediate:
        def submit(self,fn,*args):fn(*args)
        def shutdown(self,**kwargs):pass
    # Factory closures retain the original executor; use its submit method instead.
    monkeypatch.setattr(app.state.executor,'submit',lambda fn,*args:fn(*args))
    with TestClient(app) as c:
        headers={'X-TennisAI-Token':c.get('/api/bootstrap').json()['csrf_token'],'Origin':'http://testserver'}
        v=c.post('/api/videos?filename=test.mp4',content=b'SYNTHETIC',headers=headers).json()
        r=c.post('/api/videos/'+v['id']+'/runs',json={},headers=headers).json()
        yield c,headers,app,r

def test_near_default_and_no_model_call(server):
    c,h,a,r=server;r=c.get('/api/runs/'+r['id']).json()
    assert r['target']=={'position':'near','description':''}
    assert r['status']=='awaiting_report' and r['report'] is None
    assert r['provider']['kind']=='agent'
    assert c.get('/api/entry/pending').json()['runs'][0]['id']==r['id']
    assert c.post('/api/videos/'+r['video_id']+'/runs',json={'mode':'analyze'},headers=h).status_code==422

def test_origin_and_token_guard_survive_packaging(server):
    c,h,a,r=server
    assert c.post('/api/runs/'+r['id']+'/request-h5',json={},headers={**h,'Origin':'https://foreign.example'}).status_code==403
    assert c.post('/api/runs/'+r['id']+'/request-h5').status_code==403
    assert c.post('/api/runs/'+r['id']+'/request-h5',headers=h).status_code==409

def test_valid_report_and_h5_request_transition(server):
    c,h,a,r=server;m=c.get('/api/runs/'+r['id']).json()['manifest']
    assert c.post('/api/runs/'+r['id']+'/report',json=report(m),headers=h).status_code==200
    assert c.get('/api/entry/pending').json()['runs']==[]
    assert c.post('/api/runs/'+r['id']+'/request-h5',headers=h).status_code==200
    assert c.get('/api/entry/pending').json()['runs'][0]['detail_requested']
    assert c.post('/api/runs/'+r['id']+'/report',json=report(m),headers=h).status_code==409

@pytest.mark.parametrize('failure',['foreign','bad_frame','bad_time','quarter_rating','missing_reject_criterion','invented_reference','unsafe_link'])
def test_rejects_ungrounded_or_incomplete_report(server,failure):
    c,h,a,r=server;m=c.get('/api/runs/'+r['id']).json()['manifest'];body=report(m);drill=body['priorities'][0]['drill']
    if failure=='foreign':body['evidence_id']='foreign'
    if failure=='bad_frame':body['priorities'][0]['evidence'][0]['frame_id']='invented'
    if failure=='bad_time':body['priorities'][0]['evidence'][0]['timestamp']=3
    if failure=='quarter_rating':body['assessment']['rating']=3.25
    if failure=='missing_reject_criterion':drill.pop('against')
    if failure=='invented_reference':drill['source_kind']='referenced'
    if failure=='unsafe_link':drill.update(source_kind='referenced',sources=[{'title':'bad','url':'javascript:alert(1)'}])
    assert c.post('/api/runs/'+r['id']+'/report',json=body,headers=h).status_code==422
    assert c.get('/api/runs/'+r['id']).json()['report'] is None

def test_installation_tree_cannot_be_runtime_workspace():
    with pytest.raises(ValueError):main.create_app(SKILL/'runtime-data')

def test_h5_requires_real_completed_report(server):
    c,h,a,r=server
    with pytest.raises(ValueError):build(a.state.store,r)
