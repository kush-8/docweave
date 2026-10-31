from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from docweave.api.routes.github_auth import github_service,require_github_user,require_github_csrf
from docweave.api.routes.personal import project_access
from docweave.db.sessions import domain_session
from docweave.repositories import personal as repository
from docweave.schemas.personal import ConversationCreate,TurnCreate

router=APIRouter(prefix='/api/v1',tags=['Conversations'])

async def conversation_access(request,user,identity):
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        value=await repository.conversation(session,identity)
    if not value:
        raise HTTPException(404)
    await project_access(request,user,UUID(value['project_id']))
    return value

@router.get('/projects/{project_id}/conversations')
async def conversations(project_id:UUID,request:Request,user=Depends(require_github_user)):
    await project_access(request,user,project_id)
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        return {'items':await repository.list_conversations(session,project_id),'next_cursor':None}

@router.post('/projects/{project_id}/conversations',status_code=202)
async def create_conversation(project_id:UUID,body:ConversationCreate,request:Request,user=Depends(require_github_csrf)):
    project=await project_access(request,user,project_id)
    if project['repository'] is None:
        raise HTTPException(409,detail='repository_required')
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        return await repository.create_conversation(session,project_id,body.answer_profile_id or (UUID(request.app.state.runtime_config["ANSWER_PROFILE_ID"]) if request.app.state.runtime_config.get("ANSWER_PROFILE_ID") else None))

@router.get('/conversations/{conversation_id}')
async def conversation(conversation_id:UUID,request:Request,user=Depends(require_github_user)):
    return await conversation_access(request,user,conversation_id)

@router.post('/conversations/{conversation_id}/sync-retry',status_code=202)
async def retry_sync(conversation_id:UUID,request:Request,user=Depends(require_github_csrf)):
    await conversation_access(request,user,conversation_id)
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        return await repository.retry_sync(session,conversation_id)

@router.delete('/conversations/{conversation_id}',status_code=204)
async def delete_conversation(conversation_id:UUID,request:Request,user=Depends(require_github_csrf)):
    await conversation_access(request,user,conversation_id)
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        await repository.delete_conversation(session,conversation_id)
    return Response(status_code=204)

@router.get('/conversations/{conversation_id}/turns')
async def turns(conversation_id:UUID,request:Request,user=Depends(require_github_user)):
    await conversation_access(request,user,conversation_id)
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        return {'items':await repository.turns(session,conversation_id),'next_cursor':None}

@router.post('/conversations/{conversation_id}/turns',status_code=202)
async def append_turn(conversation_id:UUID,body:TurnCreate,request:Request,user=Depends(require_github_csrf)):
    await conversation_access(request,user,conversation_id)
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        return await repository.append_turn(session,conversation_id,body.idempotency_key,body.message)

@router.get('/turns/{turn_id}')
async def turn(turn_id:UUID,request:Request,user=Depends(require_github_user)):
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        result=await repository.turn(session,turn_id)
    if result is None:
        raise HTTPException(404)
    await conversation_access(request,user,UUID(result['conversation_id']))
    return result


@router.get('/turns/{turn_id}/citations/{citation_id}')
async def citation(turn_id:UUID,citation_id:str,request:Request,user=Depends(require_github_user)):
    await turn(turn_id,request,user)
    _,engine,_=github_service(request)
    async with domain_session(engine,UUID(user['id'])) as session:
        result=await repository.citation(session,turn_id,citation_id)
    if not result:
        raise HTTPException(404)
    return result
