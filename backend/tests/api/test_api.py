"""Current personal HTTP contract and safe anonymous behavior."""
import re
from pathlib import Path
from uuid import UUID
import json
from tests.paths import BACKEND_ROOT
import pytest
from openapi_spec_validator import validate

DRAFT=json.loads((BACKEND_ROOT/'openapi.yaml').read_text(encoding='utf-8'))
METHODS={'get','post','put','patch','delete'}
OPERATIONS=[(method,path,operation['operationId']) for path,methods in DRAFT['paths'].items() for method,operation in methods.items() if method in METHODS]
pytestmark=pytest.mark.anyio

def assert_error(response,status,code,retryable=False):
    assert response.status_code==status,response.text
    body=response.json()
    assert set(body)=={'code','message','request_id','retryable'}
    assert body['code']==code and body['message'] and body['retryable'] is retryable
    assert body['request_id']==response.headers['X-Request-ID']
    UUID(body['request_id'])
    assert response.headers['Cache-Control']=='no-store'

@pytest.mark.parametrize(('method','path','operation'),[item for item in OPERATIONS if not item[1].startswith(('/health/','/auth/'))])
async def test_anonymous_private_operations_are_denied(client,app,method,path,operation):
    url=re.sub(r'\{[^}]+\}','97f0d4a6-86c2-4bec-91cc-329f97d228d2',path)
    app.state.github=None;app.state.auth=None
    response=await client.request(method,'/api/v1'+url)
    if path in ('/providers','/catalog'):
        assert_error(response,503,'not_ready',True)
    else:
        assert_error(response,401,'unauthenticated')

async def test_runtime_matches_checked_contract_and_has_no_saas_domains(client):
    schema=(await client.get('/openapi.json')).json();validate(schema)
    assert set(schema['paths'])=={'/api/v1'+path for path in DRAFT['paths']}
    assert not any('/workspaces' in path or '/invitations' in path or '/grants' in path for path in schema['paths'])
    assert schema['paths']['/api/v1/auth/logout']['post']['security']==[{'sessionCookie':[],'csrfToken':[]}]
    for path in ('/workspaces','/invitations/old/accept'):
        assert_error(await client.post('/api/v1'+path,json={'private':'marker'}),404,'not_found')

async def test_readiness_liveness_and_safe_error_boundaries(client,app):
    assert_error(await client.get('/api/v1/health/ready'),503,'not_ready',True)
    first=await client.get('/api/v1/health/live',headers={'X-Request-ID':'untrusted'})
    second=await client.get('/api/v1/health/live')
    assert first.status_code==second.status_code==200
    assert first.headers['X-Request-ID']!=second.headers['X-Request-ID']
    assert_error(await client.get('/api/v1/private-marker?secret=private-marker'),404,'not_found')
    assert_error(await client.post('/api/v1/health/live'),405,'method_not_allowed')
    @app.get('/test-error',include_in_schema=False)
    async def fail():raise RuntimeError('private-marker')
    response=await client.get('/test-error')
    assert_error(response,500,'internal_error')
    assert 'private-marker' not in response.text
