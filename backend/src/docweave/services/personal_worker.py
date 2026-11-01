"""Durable personal jobs; provider execution remains explicitly admitted by its adapter."""
import json
import asyncio
import re
import time
from uuid import UUID
from cryptography.fernet import Fernet
from docweave.core.errors import DomainError
from docweave.rag.contracts import HostedError
from docweave.core.guardrails import assess_text
from docweave.integrations.stack import Dependency
from docweave.services.catalog import match_documentation, documentation_coverage
from docweave.services.turn_readiness import decide_turn_readiness
from docweave.services.project_memory import update_memory
from docweave.services.repository_sync import scan_repository
from docweave.repositories import personal as repository, catalog as catalog_repository


async def prepare_answer(turn,project,dependency_states,*,answerer=None,resolver=None):
    assessment=assess_text(turn['message'])
    if assessment.credential_blocked or assessment.injection_flagged or not assessment.complete:
        return {'status':'blocked_policy','progress':'This message contains blocked credentials or instructions. Edit it before sending.'}
    if turn.get('required_dependencies') and turn.get('context_revision')==project.get('context_revision'):
        required=turn['required_dependencies']
    elif resolver is not None:
        required=await resolver(turn,project)
    else:
        # shortcut: literal dependency references only, replace with admitted query resolution for implicit follow-ups.
        required=[entry['id'] for entry in project['stack'] if re.search(r'(?<![\w-])'+re.escape(entry['technology'])+r'(?![\w-])',turn['message'],re.I)]
    decision=decide_turn_readiness(required,dependency_states)
    status=decision['status']
    if status=='waiting_for_sources':
        return {'status':status,'required_dependencies':decision['dependency_ids'],'progress':'Building the documentation index needed for this question. It will continue automatically.'}
    if status=='failed':
        return {'status':'failed','progress':'Required documentation processing failed. Retry its ingestion before retrying the question.'}
    if status not in ('ready',):
        explanation = {
            'pending_review': 'Documentation needs approval. Review version coverage in Project documentation; unknown public sources require operator approval.',
            'consent_required': 'Processing permission is required. Review the project processing permissions.',
            'capacity': 'Documentation is waiting for processing capacity or an approved embedding profile. Check Project documentation for its status.',
            'abstain': 'Documentation is missing for this question. Review Project documentation or clarify the technology and version.',
            'clarify': 'Clarify which project technology and version this question needs.',
        }
        return {'status':'completed','answer':explanation[status],'citations':[]}
    if answerer is None:
        return {'status':'completed','answer':'I do not have eligible documentation to support an answer to this question.','citations':[]}
    return await answerer(turn,project,required)


async def run_personal_job(job_id,*,engine,settings,client,answerer=None,resolver=None,generation_id=None,answerer_factory=None):
    async with engine.connect() as connection:
        async with connection.begin():
            job=await repository.claim_job(connection,job_id)
        if not job:
            return
        project=job['project']
        project_id=UUID(project['id'])
        interrupted = False
        output={'status':'failed','progress':'Processing was interrupted.'}
        try:
            await repository.lock_project(connection,project_id)
            await connection.commit()
            async with connection.begin():
                current=await repository.job_context(connection,job_id,UUID(job['lease_token']))
            if current is None:
                return
            job.update(current)
            project=job['project']
            # No mutable branch read before the project serialization lock.
            token=json.loads(Fernet(settings.encryption_key).decrypt(job['encrypted_token'].encode()))
            if token.get('expires_at',float('inf'))<=time.time():
                raise DomainError('unauthenticated')
            access=token['access_token']
            identity=await client.user(access)
            if str(identity['id'])!=job['github_subject']:
                raise DomainError('unauthenticated')
            repo=project['repository']
            await client.repository(access,repo['repository_id'])
            if job['kind']=='sync':
                result=await scan_repository(client,access,repo['repository_id'],repo['branch'],repo['application_path'],previous_commit=repo.get('commit_sha'))
                if result['unchanged']:
                    memory={'stack':project['stack'],'stack_fingerprint':job.get('stack_fingerprint'), 'last_commit_sha':result['commit_sha'],'context_revision':project['context_revision']}
                else:
                    if not result['scan'].complete:
                        output={'status':'failed','progress':'Dependency metadata is incomplete: '+ '; '.join(result['scan'].issues[:8])+'. Correct the metadata or application folder, then retry repository synchronization.'}
                        return
                    memory=update_memory(project_id,project['stack'],job.get('stack_fingerprint'),project['context_revision'],result['scan'],result['commit_sha'])
                output={'status':'ready','expected_revision':project['context_revision'],**memory}
            else:
                async with connection.begin():
                    entries=await repository.catalog_state(connection,job_id,UUID(job['lease_token']),generation_id)
                states={}
                choices=[]
                for match in documentation_coverage(project, entries, str(generation_id) if generation_id else ''):
                    states[match['dependency_id']]={**match,'active_job':bool(match.get('entry') and match['entry'].get('active_job'))}
                    if match.get('entry') and match['status'] in ('ready','waiting_for_sources','missing'):
                        choices.append({'dependency_id':match['dependency_id'],'revision_id':str(match['entry']['revision_id'])})
                async with connection.begin():
                    await repository.select_catalog(connection,job_id,UUID(job['lease_token']),choices)
                if answerer_factory is not None:
                    async def authorize():
                        latest=await client.user(access)
                        if str(latest['id'])!=job['github_subject']:
                            raise DomainError('unauthenticated')
                        await client.repository(access,repo['repository_id'])
                        async with engine.begin() as current_connection:
                            context=await repository.job_context(current_connection,job_id,UUID(job['lease_token']))
                        if context is None or context['project']['context_revision']!=project['context_revision']:
                            raise DomainError('revision_conflict')
                    pipeline=answerer_factory(job,authorize)
                    answerer=pipeline.answer
                    resolver=pipeline.resolve
                output=await prepare_answer(job['turn'],project,states,answerer=answerer,resolver=resolver)
            await client.repository(access,repo['repository_id'])
        except asyncio.CancelledError:
            interrupted = True
            raise
        except HostedError as error:
            output={'status':'completion_unknown' if str(error)=='completion_unknown' else 'blocked_policy','progress':'The provider result is uncertain and will not be replayed automatically.' if str(error)=='completion_unknown' else 'An approved provider profile, current processing consent, or valid evidence is required.'}
        except DomainError as error:
            progress = ('GitHub is temporarily unavailable or rate limited. Retry repository synchronization later.'
                if error.code == 'not_ready' else 'Sign in with GitHub again, check App installation, repository access and branch, then retry repository synchronization.')
            output={'status':'blocked_policy','progress':progress}
        except (ValueError,KeyError):
            output={'status':'blocked_policy','progress':'Repository access or complete stack metadata could not be verified. Check setup and sign in again.'}
        except Exception:
            output={'status':'failed','progress':'Processing failed. Check service status before retrying.'}
        finally:
            try:
                if interrupted:
                    await connection.rollback()
                    # Keep the original lease/intent recoverable after shutdown.
                else:
                    async with connection.begin():
                        published=await repository.finish_job(connection,job_id,UUID(job['lease_token']),output)
                        if published and job['kind']=='sync' and output['status']=='ready':
                            entries=await catalog_repository.definitions(connection)
                            choices=[]
                            for item in output['stack']:
                                dependency=Dependency(item.get('ecosystem',''),item['technology'],documentation_target=item.get('docs_target'))
                                match=match_documentation(dependency,entries,str(generation_id) if generation_id else '')
                                if match.get('entry') and match['status']!='pending_review':
                                    choices.append({'dependency_id':item['id'],'revision_id':str(match['entry']['revision_id'])})
                            await catalog_repository.reconcile(connection,project_id,UUID(job['actor_id']),choices,generation_id)
            finally:
                await repository.unlock_project(connection,project_id)
                await connection.commit()
