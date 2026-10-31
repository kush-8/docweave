from docweave.storage.artifacts import ArtifactStore
from docweave.core.settings import storage_root


def storage(request):
    if not hasattr(request.app.state, "ingestion_store"):
        request.app.state.ingestion_store = ArtifactStore(storage_root())
    return request.app.state.ingestion_store
