"""Type-aware relationships for any valid CSV shape, without misleading numeric guesses."""
from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from datamendry.api import create_app, Settings
from datamendry.smart_relationships import PROFILE_ROWS, PAIR_ROWS

ROOT = Path(__file__).resolve().parents[1]


def upload(client, data: bytes):
    response = client.post('/api/datasets',files={'file':('relationships.csv', data, 'text/csv')})
    assert response.status_code == 201, response.text
    return response.json()['dataset_id']


def test_employee_style_csv_auto_falls_back_for_identifiers_but_compares_categories(tmp_path):
    app = create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    data = b'Index,First Name,Last Name,Sex,Email,Job Title\n1,Jo,Pat,Female,jo@example.com,Analyst\n2,Raj,Pat,Male,raj@example.com,Engineer\n3,Mia,Lee,Female,mia@example.com,Analyst\n4,Tom,Lee,Male,tom@example.com,Engineer\n'
    with TestClient(app) as client:
        ds = upload(client, data)
        info = client.get(f'/api/datasets/{ds}/smart/overview')
        assert info.status_code == 200
        kinds = {c['name']:c['kind'] for c in info.json()['columns']}
        assert kinds['Index'] == 'identifier'
        assert kinds['Email'] == 'identifier'
        assert kinds['First Name'] == 'identifier'
        assert kinds['Sex'] == 'category'
        assert kinds['Job Title'] == 'category'
        assert info.json()['suggested'] == ['Job Title','Sex'] or set(info.json()['suggested']) == {'Sex','Job Title'}
        result = client.get(f'/api/datasets/{ds}/smart/pair',params={'x':'Sex','y':'Job Title'})
        assert result.status_code == 200
        assert result.json()['mode'] == 'category_category'
        assert result.json()['cramers_v'] == 1
        assert sum(map(sum,result.json()['cells'])) == 4
        private = client.get(f'/api/datasets/{ds}/smart/pair',params={'x':'First Name','y':'Email'}).json()
        assert private['mode']=='quality'
        assert 'jo@example.com' not in str(private)
        assert 'Raj' not in str(private)


def test_numeric_categorical_grouping_aggregates_correctly(tmp_path):
    app = create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as client:
        ds=upload(client,b'Score,Team\n10,Blue\n20,Blue\n30,Red\n40,Red\n')
        payload=client.get(f'/api/datasets/{ds}/smart/pair',params={'x':'Score','y':'Team'}).json()
        assert payload['mode']=='category_numeric'
        groups={g['category']:g for g in payload['groups']}
        assert groups['Blue']['mean']==15
        assert groups['Red']['mean']==35
        assert all(g['count']==2 for g in groups.values())


def test_numeric_numeric_pearson_works_without_changing_old_route(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as client:
        ds=upload(client,b'CGPA,IQ\n5,20\n6,30\n7,40\n8,50\n')
        p=client.get(f'/api/datasets/{ds}/smart/pair',params={'x':'CGPA','y':'IQ'}).json()
        assert p['mode']=='numeric_numeric'
        assert p['r']==pytest.approx(1.0)
        assert sum(map(sum,p['bins']))==4
        assert client.get(f'/api/datasets/{ds}/relationships').status_code==200


def test_date_numeric_monthly_mean(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as client:
        ds=upload(client,b'Order Date,Revenue\n2025-01-01,10\n2025-01-15,30\n2025-02-02,50\n2025-02-15,70\n')
        p=client.get(f'/api/datasets/{ds}/smart/pair',params={'x':'Revenue','y':'Order Date'}).json()
        assert p['mode']=='date_numeric'
        assert [v['mean'] for v in p['months']]==[20,60]
        assert p['metrics']['months_total']==2


def test_date_category_trend(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as client:
        ds=upload(client,b'Event Date,Region\n2025-01-01,West\n2025-01-02,East\n2025-02-01,West\n2025-02-05,West\n')
        p=client.get(f'/api/datasets/{ds}/smart/pair',params={'x':'Event Date','y':'Region'}).json()
        assert p['mode']=='date_category'
        assert p['metrics']['paired_values']==4
        assert sum(map(sum,[r['counts'] for r in p['months']]))==4


def test_date_date_differences(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as client:
        ds=upload(client,b'Start Date,End Date\n2025-01-01,2025-01-05\n2025-01-02,2025-01-10\n2025-01-03,2025-01-07\n')
        p=client.get(f'/api/datasets/{ds}/smart/pair',params={'x':'Start Date','y':'End Date'}).json()
        assert p['mode']=='date_date'
        assert p['metrics']['mean_difference_days']==(4+8+4)/3


def test_single_column_and_all_blank_are_graceful(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as client:
        ds=upload(client,b'Note\nhello\nworld\n')
        info=client.get(f'/api/datasets/{ds}/smart/overview').json()
        assert len(info['columns'])==1
        assert not info['suggested'] or len(info['suggested'])==1
        assert client.get(f'/api/datasets/{ds}/smart/pair?x=Note&y=Note').status_code==422
        ds2=upload(client,b'X,Y\n,\n,\n')
        p=client.get(f'/api/datasets/{ds2}/smart/pair?x=X&y=Y').json()
        assert p['mode']=='quality'


def test_high_cardinality_string_pair_uses_privacy_aware_quality(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    raw='Review,Other\n'+''.join(f'confidential-note-{i},unique-{i}\n' for i in range(100))
    with TestClient(app) as client:
        ds=upload(client,raw.encode())
        p=client.get(f'/api/datasets/{ds}/smart/pair?x=Review&y=Other').json()
        assert p['mode']=='quality'
        assert 'confidential-note-' not in str(p)
        assert p['data_sent_externally'] is False


def test_limited_samples_and_no_raw_records(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    csv=b'Team,Score\n'+b''.join(f"{'X' if i%2 else 'Y'},{i}\n".encode() for i in range(PROFILE_ROWS+2))
    with TestClient(app) as client:
        ds=upload(client,csv)
        info=client.get(f'/api/datasets/{ds}/smart/overview').json()
        assert info['sampled_rows']==PROFILE_ROWS and info['truncated'] is True
        p=client.get(f'/api/datasets/{ds}/smart/pair?x=Team&y=Score').json()
        assert p['sampled_rows']==PROFILE_ROWS+2
        assert 'rows' not in p and 'raw_data' not in p


def test_invalid_column_and_cross_session_access(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as owner,TestClient(app) as outsider:
        ds=upload(owner,b'A,B\n1,x\n2,y\n3,z\n')
        assert outsider.get(f'/api/datasets/{ds}/smart/overview').status_code==404
        assert outsider.get(f'/api/datasets/{ds}/smart/pair?x=A&y=B').status_code==404
        assert owner.get(f'/api/datasets/{ds}/smart/pair?x=A&y=missing').status_code==422
        assert owner.get(f'/api/datasets/{ds}/smart/pair?x=A&y=A').status_code==422


def test_m7_ui_and_asset_allowlist_preserves_prior_options(tmp_path):
    html=(ROOT/'static/index.html').read_text(encoding='utf-8')
    js=(ROOT/'static/smart_analytics.js').read_text(encoding='utf-8')
    for marker in ['value="single" selected','value="all"','value="compare"','id="analytics-smart-controls"','id="analytics-smart-result"','/static/smart_analytics.js']:
        assert marker in html
    assert '.replaceChildren(' in js and '.textContent =' in js
    assert 'innerHTML' not in js
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as client:
        assert client.get('/static/smart_analytics.js').status_code==200
        assert client.get('/static/analytics.js').status_code==200
        assert client.get('/static/account.js').status_code==200


def test_failed_comparison_never_changes_source(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    with TestClient(app) as client:
        ds=upload(client,b'A,B\n1,X\n2,Y\n3,X\n')
        before=client.get(f'/api/datasets/{ds}/preview').json()
        assert client.get(f'/api/datasets/{ds}/smart/pair?x=A&y=B').status_code==200
        after=client.get(f'/api/datasets/{ds}/preview').json()
        assert before==after


def test_generic_column_email_values_get_privacy_protection(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    csv=b'A,Group\nlee@example.com,Red\nraj@example.com,Blue\nlee@example.com,Red\nraj@example.com,Blue\n'
    with TestClient(app) as client:
        ds=upload(client,csv)
        info=client.get(f'/api/datasets/{ds}/smart/overview').json()
        assert info['columns'][0]['kind']=='identifier'
        p=client.get(f'/api/datasets/{ds}/smart/pair?x=A&y=Group').json()
        assert p['mode']=='quality'
        assert 'lee@example.com' not in str(p)
        assert p['columns'][0]['unique']==2


def test_categorical_high_cardinality_groups_other_without_inferential_claim(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    csv='Group,Segment\n'+''.join(f'G{i},S{i%3}\n' for i in range(12))
    with TestClient(app) as client:
        ds=upload(client,csv.encode())
        p=client.get(f'/api/datasets/{ds}/smart/pair?x=Group&y=Segment').json()
        assert p['mode']=='category_category'
        assert p['categories_collapsed'] is True
        assert p['cramers_v'] is None
        assert sum(map(sum,p['cells']))==12


def test_pair_sampling_is_capped_at_10000(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data',demo_only=False))
    csv=('Team,Score\n'+''.join(f'{"A" if i%2 else "B"},{i}\n' for i in range(PAIR_ROWS+3))).encode()
    with TestClient(app) as client:
        ds=upload(client,csv)
        p=client.get(f'/api/datasets/{ds}/smart/pair?x=Team&y=Score').json()
        assert p['sampled_rows']==PAIR_ROWS and p['truncated'] is True
        assert p['metrics']['paired_values']==PAIR_ROWS
