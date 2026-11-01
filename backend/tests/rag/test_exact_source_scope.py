import socket
import pytest
from docweave.integrations.public_sources import validated_address


def public_address(*args, **kwargs):
    return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]


def test_root_and_exact_page_scope_keep_the_actual_publisher_url():
    root={'origin':'https://docs.example.org','path_prefix':'/'}
    assert validated_address('https://docs.example.org',root,resolver=public_address)[0]=='docs.example.org'
    exact={**root,'path_prefix':'/guide'}
    assert validated_address('https://docs.example.org/guide',exact,resolver=public_address)
    with pytest.raises(ValueError):
        validated_address('https://docs.example.org/guide/other',exact,resolver=public_address)
