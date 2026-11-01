import pytest


@pytest.mark.anyio
async def test_publisher_discovery_and_private_review_require_authentication(client):
    path='/api/v1/projects/00000000-0000-4000-8000-000000000001/documentation/dependency'
    for operation in ('discover', 'review-source'):
        response=await client.post(path+'/'+operation,json={'expected_revision':1,'allow_public_lookup':True})
        assert response.status_code==401,response.text
