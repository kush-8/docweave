from pathlib import Path
from fastapi import HTTPException
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.datastructures import UploadFile
from docweave.rag.contracts import MAX_BYTES


async def bounded_upload(request):
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
        raise HTTPException(422)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BYTES + 65536:
            raise HTTPException(413)
        body.extend(chunk)
    async def stream():
        yield bytes(body)
    try:
        form = await MultiPartParser(request.headers, stream(), max_files=1, max_fields=0).parse()
    except (MultiPartException, ValueError):
        raise HTTPException(422) from None
    try:
        values = form.getlist("file")
        if len(form) != 1 or len(values) != 1 or not isinstance(values[0], UploadFile):
            raise HTTPException(422)
        file = values[0]
        name = file.filename or ""
        if not 1 <= len(name) <= 200 or any(c in name for c in ("/", "\\", "\x00")) or name.startswith("."):
            raise HTTPException(422)
        media = file.content_type
        if (Path(name).suffix.lower(), media) not in ((".txt", "text/plain"), (".md", "text/markdown"), (".markdown", "text/markdown")):
            raise HTTPException(422)
        content = await file.read(MAX_BYTES + 1)
        if not content or len(content) > MAX_BYTES:
            raise HTTPException(422)
        return name, media, content
    finally:
        await form.close()
