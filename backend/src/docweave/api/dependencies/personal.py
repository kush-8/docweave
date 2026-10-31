from uuid import UUID
from fastapi import Depends,HTTPException,Request
from docweave.api.routes.github_auth import require_github_user,github_service
from docweave.api.routes.personal import project_access
from docweave.core.identity import Actor
from docweave.db.sessions import domain_session
from docweave.repositories import personal as repository

async def resource_actor(request:Request,user=Depends(require_github_user)):
    kind,raw=next((kind,request.path_params[kind+'_id']) for kind in ('project','collection','document','job','source') if kind+'_id' in request.path_params)
    try:
        identity=UUID(raw)
    except (TypeError,ValueError):
        raise HTTPException(404) from None
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        context=await repository.resource(session,kind,identity)
    if context is None:
        raise HTTPException(404)
    await project_access(request,user,UUID(context['project_id']))
    return Actor(UUID(user['id']),UUID(context['workspace_id']) if context['workspace_id'] else None)
