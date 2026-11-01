import pytest


@pytest.mark.anyio
async def test_reference_catalog_exposes_all_29_without_claiming_version_eligibility(client):
    response=await client.get('/api/v1/catalog/references')
    assert response.status_code==200,response.text
    entries=response.json()['items']
    assert len(entries)==29
    assert all(entry['version_coverage']['package_match_eligible'] is False for entry in entries)
    assert all(entry['pages'] and entry['attribution'] for entry in entries)
