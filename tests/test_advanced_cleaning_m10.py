"""Milestone 10: preview-first targeted transformations and session isolation."""
import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from datamendry.api import Settings, create_app
from datamendry.advanced_cleaning import validate_steps, apply_row

SAMPLE = ("ID,Name,Score,Region\n"
          "1,  ALICE ,7.567,  \n"
          "2,BOB ,oops,East\n"
          "3,=1+1,8.123,\n").encode()


def app(tmp_path):
    return create_app(Settings(data_dir=tmp_path/'data',demo_only=False))


def upload(c):
    r = c.post('/api/datasets', files={'file':('data.csv',SAMPLE,'text/csv')})
    assert r.status_code == 201, r.text
    return r.json()['dataset_id']


def urls(ds):
    return f'/api/datasets/{ds}/advanced/preview', f'/api/datasets/{ds}/advanced/export'


def test_plan_previews_exact_changes_and_does_not_modify_original(tmp_path):
    with TestClient(app(tmp_path)) as c:
        ds=upload(c)
        steps=[{'action':'fill_blank','column':'Region','value':'Unknown'},
               {'action':'titlecase','column':'Name'},
               {'action':'round_number','column':'Score','places':2}]
        prev,exp=urls(ds)
        r=c.post(prev,json={'steps':steps})
        assert r.status_code==200, r.text
        data=r.json()
        assert data['row_count']==3 and data['skipped_numeric']==1
        assert data['rows'][0]['before']==['1','  ALICE ','7.567','  ']
        assert data['rows'][0]['after']==['1','  Alice ','7.57','Unknown']
        assert data['rows'][0]['changed_columns']==[1,2,3]
        assert data['rows'][1]['after'][2]=='oops'
        assert data['changed_cells']==6
        assert data['source_unchanged'] is True
        assert c.get(f'/api/datasets/{ds}/preview').json()['rows'][0][1]=='  ALICE '
        out=c.post(exp,json={'steps':steps,'preview_token':data['preview_token']})
        assert out.status_code==200, out.text
        rows=list(csv.reader(io.StringIO(out.content.decode('utf-8-sig'))))
        assert rows[1]==['1','  Alice ','7.57','Unknown']
        assert rows[2][2]=='oops'
        assert rows[3][1].endswith('=1+1') and rows[3][1]!='=1+1'
        assert c.get(f'/api/datasets/{ds}/preview').json()['rows'][0][1]=='  ALICE '


def test_single_step_supported(tmp_path):
    with TestClient(app(tmp_path)) as c:
        ds=upload(c)
        prev,_=urls(ds)
        got=c.post(prev,json={'steps':[{'action':'lowercase','column':'Name'}]})
        assert got.status_code==200 and got.json()['row_count']==3


@pytest.mark.parametrize('steps',[[],[{'action':'fill_blank','column':'NOT_REAL','value':'X'}],
    [{'action':'fill_blank','column':'Region','value':'  '}],
    [{'action':'replace_literal','column':'Name','value':''}],
    [{'action':'round_number','column':'Score','places':7}],
    [{'action':'uppercase','column':'Name','value':'oops'}],
    [{'action':'fill_blank','column':'Region','value':'x'*151}],
    [{'action':'lowercase','column':'Name'}]*7,
])
def test_rejects_bad_steps(tmp_path,steps):
    with TestClient(app(tmp_path)) as c:
        ds=upload(c)
        prev,_=urls(ds)
        assert c.post(prev,json={'steps':steps}).status_code==422


def test_rejects_export_without_preview_or_changed_plan(tmp_path):
    with TestClient(app(tmp_path)) as c:
        ds=upload(c)
        prev,exp=urls(ds)
        steps=[{'action':'uppercase','column':'Name'}]
        assert c.post(exp,json={'steps':steps}).status_code==403
        token=c.post(prev,json={'steps':steps}).json()['preview_token']
        assert c.post(exp,json={'steps':[{'action':'lowercase','column':'Name'}],'preview_token':token}).status_code==403
        assert c.post(exp,json={'steps':steps,'preview_token':token}).status_code==200


def test_different_browser_cannot_read_preview_or_export(tmp_path):
    application=app(tmp_path)
    with TestClient(application) as a, TestClient(application) as b:
        ds=upload(a)
        prev,exp=urls(ds)
        steps=[{'action':'lowercase','column':'Name'}]
        token=a.post(prev,json={'steps':steps}).json()['preview_token']
        assert b.post(prev,json={'steps':steps}).status_code==404
        assert b.post(exp,json={'steps':steps,'preview_token':token}).status_code==404


def test_text_replacement_literal_and_sequential():
    ops=validate_steps(['Name','Code'],[{'action':'replace_literal','column':'Name','value':'-', 'replacement':' '},
                                             {'action':'titlecase','column':'Name'}])
    after,changed,skipped=apply_row(['hello-world','123'],ops)
    assert after==['Hello World','123'] and changed==[0] and skipped==0


def test_static_assets_and_repair_controls(tmp_path):
    with TestClient(app(tmp_path)) as c:
        resp=c.get('/static/advanced_cleaning.js')
        assert resp.status_code==200 and b'advanced-preview' in resp.content
        page=c.get('/').text
        for token in ['id="advanced-action"','id="advanced-before"','id="advanced-after"','id="advanced-undo"','id="advanced-redo"']:
            assert token in page


def test_formula_guard_on_fill_value(tmp_path):
    with TestClient(app(tmp_path)) as c:
        ds=upload(c)
        prev,exp=urls(ds)
        steps=[{'action':'fill_blank','column':'Region','value':'=HYPERLINK("http://bad")'}]
        token=c.post(prev,json={'steps':steps}).json()['preview_token']
        out=c.post(exp,json={'steps':steps,'preview_token':token})
        rows=list(csv.reader(io.StringIO(out.content.decode('utf-8-sig'))))
        assert rows[1][3].startswith('\t=HYPERLINK(')


def test_proposal_is_not_a_database_mutation(tmp_path):
    with TestClient(app(tmp_path)) as c:
        ds=upload(c)
        prev,_=urls(ds)
        before=c.get(f'/api/datasets/{ds}/analytics',params={'column':'Name'}).json()
        r=c.post(prev,json={'steps':[{'action':'uppercase','column':'Name'}]})
        assert r.status_code==200
        after=c.get(f'/api/datasets/{ds}/analytics',params={'column':'Name'}).json()
        assert before==after
