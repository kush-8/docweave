"""Explicit embedding selection; existing Gemini generations remain usable."""
from docweave.integrations import gemini, openai
from docweave.rag.contracts import HostedError

def embedding_backend(config):
    provider=config.get('EMBEDDING_PROVIDER','gemini')
    if provider=='openai':
        return openai
    if provider=='gemini':
        return gemini
    raise HostedError('provider_unavailable')
