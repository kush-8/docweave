from dataclasses import asdict
import json
from uuid import uuid4
import pytest
from docweave.core.guardrails import assess_text
from docweave.storage.artifacts import ArtifactStore


def test_review_page_verifies_artifact_and_bounds_visible_content(tmp_path):
    from docweave.services.guardrails import review_page
    version=uuid4()
    content='a'*16001
    store=ArtifactStore(tmp_path)
    assessment=asdict(assess_text(content,document_version=str(version),parser_config={'configuration':'fixture'}))
    snapshot={**assessment,'document_version_id':str(version)}
    store.put(version,json.dumps({'text':content,'configuration':'fixture'}).encode())
    page=review_page(store,snapshot,0)
    assert len(page['text'])==16000 and page['next_offset']==16000
    assert review_page(store,snapshot,16000)['text']=='a'
    assert review_page(store,snapshot,16000)['next_offset'] is None
    with pytest.raises(ValueError):
        review_page(store,{**snapshot,'content_hash':'0'*64},0)
    with pytest.raises(ValueError):
        review_page(store,{**snapshot,'parser_config_hash':'0'*64},0)
    with pytest.raises(ValueError):
        review_page(store,snapshot,-1)
