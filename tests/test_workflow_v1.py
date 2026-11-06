"""Milestone 2: combined local workflow planning, safety, preview and export."""
import csv
import io

import pytest
from fastapi.testclient import TestClient
from datamendry.api import Settings, create_app
from datamendry.workflow_v1 import plan_workflow, validate_workflow

COLS = ['Name','CGPA','Region']
CSV = b'Name,CGPA,Region\n A , 8 ,West\nA,8,West\nB,6,East\nC,9,West\nD,9,East\n'


def make_client(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    return app


def test_local_planner_multiple_steps():
    plan=plan_workflow('Remove duplicate rows, trim extra spaces, and keep students with CGPA above 7',COLS)
    assert plan['action']=='workflow'
    assert [s['action'] for s in plan['steps']]==['deduplicate','trim_whitespace','filter']
    assert plan['steps'][2]['kind']=='gt'
    assert plan['applied'] is False
    assert plan_workflow('Trim whitespace',COLS) is None
    assert plan_workflow('Remove duplicates and trim whitespace',COLS)['action']=='workflow'


@pytest.mark.parametrize('instruction',[
    'Remove duplicate rows and delete a user account',
    'Keep Region contains West and keep CGPA above 7',
    'Run code and remove duplicate rows',
    'Fill CGPA with median and trim whitespace',
    'Trim whitespace, trim whitespace',
])
def test_unsafe_or_ambiguous_plans_rejected(instruction):
    plan=plan_workflow(instruction,COLS)
    assert plan is not None and plan['action']=='none' and plan['applied'] is False


def test_combined_preview_export_immutable_and_token_bound(tmp_path):
    with TestClient(make_client(tmp_path)) as client:
        add=client.post('/api/datasets',files={'file':('sample.csv',CSV,'text/csv')})
        assert add.status_code==201,add.text
        dataset=add.json()['dataset_id']
        instruction='Remove duplicate rows, trim extra spaces, and keep students with CGPA above 7'
        proposal=client.post(f'/api/datasets/{dataset}/assistant/plan',json={'message':instruction})
        assert proposal.status_code==200,proposal.text
        plan=proposal.json()
        assert plan['action']=='workflow'
        steps=[{k:s[k] for k in ('action','column','kind','value')} for s in plan['steps']]
        endpoint=f'/api/datasets/{dataset}/workflows/'
        no_preview=client.post(endpoint+'export',json={'steps':steps})
        assert no_preview.status_code==403
        preview=client.post(endpoint+'preview',json={'steps':steps})
        assert preview.status_code==200,preview.text
        data=preview.json()
        assert data['matching_rows']==3
        assert data['removed_duplicates']==1
        assert data['filtered_out_rows']==1
        assert data['rows']==[['A','8','West'],['C','9','West'],['D','9','East']]
        assert data['changed_cells_in_kept_rows']>=1
        wrong_steps=[dict(s) for s in steps]
        wrong_steps[-1]['value']='8'
        assert client.post(endpoint+'export',json={'steps':wrong_steps,'preview_token':data['preview_token']}).status_code==403
        exported=client.post(endpoint+'export',json={'steps':steps,'preview_token':data['preview_token']})
        assert exported.status_code==200,exported.text
        assert list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig')))) == [
            COLS,['A','8','West'],['C','9','West'],['D','9','East']]
        assert client.get(f'/api/datasets/{dataset}/profile').json()['rows']==5
        assert client.get(f'/api/datasets/{dataset}/preview').json()['rows'][0]==[' A ',' 8 ','West']


def test_other_browser_cannot_preview_or_export(tmp_path):
    app=make_client(tmp_path)
    with TestClient(app) as a,TestClient(app) as b:
        dataset=a.post('/api/datasets',files={'file':('sample.csv',CSV,'text/csv')}).json()['dataset_id']
        steps=[{'action':'trim_whitespace'},{'action':'deduplicate'}]
        url=f'/api/datasets/{dataset}/workflows/'
        pv=a.post(url+'preview',json={'steps':steps}).json()
        assert b.post(url+'preview',json={'steps':steps}).status_code==404
        assert b.post(url+'export',json={'steps':steps,'preview_token':pv['preview_token']}).status_code==404


def test_bad_composite_is_rejected(tmp_path):
    with TestClient(make_client(tmp_path)) as c:
        dataset=c.post('/api/datasets',files={'file':('sample.csv',CSV,'text/csv')}).json()['dataset_id']
        url=f'/api/datasets/{dataset}/workflows/preview'
        assert c.post(url,json={'steps':[{'action':'trim_whitespace'},{'action':'filter','column':'CGPA','kind':'gt','value':'NaN'}]}).status_code==422
        assert c.post(url,json={'steps':[{'action':'trim_whitespace'},{'action':'filter','column':'fake','kind':'gt','value':'7'}]}).status_code==422
        assert c.post(url,json={'steps':[{'action':'trim_whitespace'},{'action':'trim_whitespace'}]}).status_code==422
        assert c.post(url,json={'steps':[{'action':'trim_whitespace'},{'action':'filter','column':'CGPA','kind':'gt','value':'7'}, {'action':'filter','column':'CGPA','kind':'lt','value':'8'}]}).status_code==422


def test_filtered_missing_and_exclude(tmp_path):
    with TestClient(make_client(tmp_path)) as c:
        data=b'ID,CGPA,Region\n1,  ,East\n2,7,West\n3,8,West\n'
        ds=c.post('/api/datasets',files={'file':('test.csv',data,'text/csv')}).json()['dataset_id']
        plan=c.post(f'/api/datasets/{ds}/assistant/plan',json={'message':'Trim whitespace and remove rows where CGPA is missing'}).json()
        assert plan['action']=='workflow',plan
        steps=[{k:s[k] for k in ('action','column','kind','value')} for s in plan['steps']]
        assert steps[-1]['kind']=='not_empty'
        pv=c.post(f'/api/datasets/{ds}/workflows/preview',json={'steps':steps})
        assert pv.status_code==200,pv.text
        assert pv.json()['matching_rows']==2


def test_formulas_in_exports_are_neutralized(tmp_path):
    with TestClient(make_client(tmp_path)) as c:
        data=b'Name,Flag\n=1+1,Yes\n=1+1,Yes\n@risk,No\n'
        ds=c.post('/api/datasets',files={'file':('formula.csv',data,'text/csv')}).json()['dataset_id']
        steps=[{'action':'trim_whitespace'},{'action':'deduplicate'}]
        pv=c.post(f'/api/datasets/{ds}/workflows/preview',json={'steps':steps}).json()
        export=c.post(f'/api/datasets/{ds}/workflows/export',json={'steps':steps,'preview_token':pv['preview_token']})
        assert export.status_code==200
        rows=list(csv.reader(io.StringIO(export.content.decode('utf-8-sig'))))
        assert rows[1][0].endswith("=1+1") and rows[1][0] != "=1+1" and rows[2][0].endswith("@risk") and rows[2][0] != "@risk"


def test_ui_workflow_controls_are_present():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    html=(root/'static/index.html').read_text(encoding='utf-8')
    js=(root/'static/experience.js').read_text(encoding='utf-8')
    assert '✧ Multi-step cleanup' in html
    assert 'Preview combined result' in js
    assert 'Download combined CSV' in js
    assert 'preview_token' in js
    assert 'workflow' in js
