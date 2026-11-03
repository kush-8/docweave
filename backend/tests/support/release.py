"""Offline release fixtures; never provision approvals or synthetic indexes in development."""
import json
import hashlib
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import text
from docweave.core.guardrails import assess_text
from docweave.evaluation.frozen import load_frozen_sources, read_bounded
from docweave.rag.contracts import CONFIGURATION
from docweave.rag.parsing import parse_text
from docweave.rag.tokenization import count_evidence_tokens
from docweave.repositories.ownership import require_migration_role


async def _document(connection, store, collection, parsed, generation, *, url=None, source=None):
    identity = await connection.scalar(text("INSERT INTO app.documents(collection_id,source_id,title,media_type) VALUES(:c,:s,'Offline release fixture',:media) RETURNING id"),
        {'c': collection, 's': source, 'media': parsed['configuration'].rsplit(':', 1)[-1]})
    version = await connection.scalar(text('INSERT INTO app.document_versions(document_id,content_hash,configuration,source_url) VALUES(:d,:hash,:config,:url) RETURNING id'),
        {'d': identity, 'hash': parsed['sha256'], 'config': parsed['configuration'], 'url': url})
    store.put(version, json.dumps(parsed).encode())
    await connection.execute(text("UPDATE app.documents SET active_version_id=:v,status='ready' WHERE id=:d"), {'v': version, 'd': identity})
    assessment = assess_text(parsed['text'], parser_config={'configuration': parsed['configuration']})
    await connection.execute(text("""INSERT INTO app.document_assessments(document_version_id,content_hash,parser_config_hash,rule_revision,policy_epoch,credential_blocked,injection_flagged,complete,findings)
        VALUES(:v,:hash,:config,:rule,(SELECT epoch FROM app.guardrail_policy),:credentials,:injection,:complete,CAST(:findings AS jsonb))"""),
        {'v': version, 'hash': assessment.content_hash, 'config': assessment.parser_config_hash, 'rule': assessment.rule_revision,
         'credentials': assessment.credential_blocked, 'injection': assessment.injection_flagged, 'complete': assessment.complete,
         'findings': json.dumps(assessment.findings)})
    await connection.execute(text('INSERT INTO app.document_indexes(document_id,generation_id,document_version_id) VALUES(:d,:g,:v)'), {'d': identity, 'g': generation, 'v': version})
    chunks = []
    for span in parsed['chunks']:
        quote = parsed['text'][span['start']:span['end']]
        chunk = await connection.scalar(text("""INSERT INTO app.chunks(collection_id,project_id,document_id,document_version_id,generation_id,start_offset,end_offset,heading,line_start,line_end,content,terms,token_count,embedding,source_url,captured_at,provenance)
            VALUES(:c,(SELECT project_id FROM app.collections WHERE id=:c),:d,:v,:g,:start,:end,:heading,:line_start,:line_end,:quote,app.bm25_terms(:quote),:tokens,CAST(:vector AS public.vector),:url,now(),jsonb_build_object('offline_fixture',true,'normalized_sha256',CAST(:hash AS text))) RETURNING id"""),
            {'c': collection, 'd': identity, 'v': version, 'g': generation, **span, 'quote': quote,
             'tokens': count_evidence_tokens(quote), 'vector': str([1.0]+[0.0]*767), 'url': url, 'hash': parsed['sha256']})
        chunks.append(chunk)
    return identity, version, chunks


async def materialize_release_cases(connection, dataset, folder, actor, other_actor, store):
    url = connection.engine.url
    if (url.host, url.port, url.database) != ('127.0.0.1', 55433, 'docweave_test') or url.query:
        raise ValueError('Offline fixtures require the isolated test database')
    if not connection.in_transaction():
        raise ValueError('Offline fixture setup requires one caller-owned transaction')
    await require_migration_role(connection)
    actor, other_actor = UUID(str(actor)), UUID(str(other_actor))
    if actor == other_actor or await connection.scalar(text("SELECT count(*) FROM app.users WHERE id IN (:a,:b) AND issuer='https://github.com' AND subject ~ '^[0-9]+$'"), {'a': actor, 'b': other_actor}) != 2:
        raise ValueError('Two distinct fixture GitHub actors are required')
    if any(store.root.iterdir()):
        raise ValueError('Offline fixtures require an empty artifact directory')
    parsed = load_frozen_sources(dataset, folder)
    manifest_bytes = read_bounded(Path(folder) / 'manifest.json', 1024*1024)
    manifest = json.loads(manifest_bytes)
    raw_hashes = {url: receipt['raw_sha256'] for url, receipt in manifest['sources'].items()}
    if set(parsed) != {url for case in dataset.cases for url in case.sources}:
        raise ValueError('All dataset sources must be frozen')
    await connection.execute(text("INSERT INTO app.processors(id,provider,backend,roles,enabled) VALUES('test:offline-release:openai:v1','openai','offline-fixture','[\"embedding\"]',true) ON CONFLICT(id) DO UPDATE SET enabled=true"))
    generation = await connection.scalar(text("INSERT INTO app.index_generations(model,backend,dimensions,normalization,chunker,processor_ids,enabled) VALUES('text-embedding-3-small','offline-fixture',768,'unit-l2',:config,'[\"test:offline-release:openai:v1\"]',true) RETURNING id"), {'config': CONFIGURATION})
    catalogs, setups = {}, {}
    for case in dataset.cases:
        owner = other_actor if case.kind == 'denied' else actor
        target = case.project_context.docs_target
        source_target = target
        sources = list(case.sources)
        if case.kind == 'version':
            if case.id == 'react-exact-old-version':
                target = '16.7.0'
                reference = next(item for item in dataset.cases if item.project_context.technology == 'react' and item.sources)
                source_target, sources = reference.project_context.docs_target, list(reference.sources)
            elif case.id == 'policy-unaccepted-version':
                target, source_target = '2.1', '5.x'
                sources = ['https://fixture.invalid/widgetdb/5/guide']
                raw = b'Synthetic WidgetDB 5.x guide; compatibility with 2.1 is not established.'
                parsed[sources[0]] = parse_text(raw, 'text/plain')
                raw_hashes[sources[0]] = hashlib.sha256(raw).hexdigest()
            else:
                raise ValueError('Version fixture needs explicit installed/source targets')
        ecosystem = 'javascript' if case.project_context.technology in {'typescript', 'react', 'nextjs', 'vite', 'tailwindcss', 'nodejs'} else 'python'
        opaque = hashlib.sha256(case.id.encode()).hexdigest()[:16]
        dependency = {'id': 'dependency-'+opaque, 'technology': case.project_context.technology, 'ecosystem': ecosystem, 'docs_target': target}
        repository_id = 43 if case.id == 'policy-denied-evidence' else 42
        project = await connection.scalar(text("""INSERT INTO app.projects(owner_user_id,name,goal,stack,repository_id,repository_branch,application_path,last_commit_sha,sync_status,constraints)
            VALUES(:owner,:name,'Offline release scenario',CAST(:stack AS jsonb),:repository,'main','',:sha,'ready',:constraints) RETURNING id"""),
            {'owner': owner, 'name': 'Project '+opaque, 'stack': json.dumps([dependency]), 'sha': 'a'*40, 'repository': repository_id, 'constraints': case.project_context.constraints})
        default = await connection.scalar(text("INSERT INTO app.collections(project_id,name,is_default) VALUES(:p,'Offline private scope',true) RETURNING id"), {'p': project})
        conversation = await connection.scalar(text("INSERT INTO app.conversations(project_id,status) VALUES(:p,'ready') RETURNING id"), {'p': project})
        state = {'project_id': str(project), 'conversation_id': str(conversation), 'default_collection_id': str(default),
            'collection_ids': [], 'catalog_revision_ids': [], 'installed_target': target, 'source_target': source_target,
            'fallback_accepted': False, 'source_guardrail_blocked': [], 'repository_id': repository_id}
        for source_url in sources:
            key = (case.project_context.technology, source_target, source_url)
            if key not in catalogs:
                snapshot = parsed[source_url]
                parts = urlsplit(source_url)
                revision = await connection.scalar(text("""INSERT INTO app.public_catalog_revisions(technology,ecosystem,docs_target,coverage,origin,path_prefix,source_url,attribution,source_hash,enabled,source_approved)
                    VALUES(:tech,:ecosystem,:target,CAST(:coverage AS jsonb),:origin,:path,:url,'Offline fixture only',:hash,true,true) RETURNING id"""),
                    {'tech': case.project_context.technology, 'ecosystem': ecosystem, 'target': source_target, 'coverage': json.dumps({'granularity': 'exact', 'version': source_target}),
                     'origin': 'https://'+parts.netloc, 'path': parts.path, 'url': source_url, 'hash': raw_hashes[source_url]})
                collection = await connection.scalar(text("INSERT INTO app.collections(catalog_revision_id,name) VALUES(:r,'Offline public scope') RETURNING id"), {'r': revision})
                selection = await connection.scalar(text("""INSERT INTO app.documentation_selections(catalog_revision_id,approved_by,technology,docs_target,coverage,origin,path_prefix,source_url,attribution)
                    SELECT id,:actor,technology,docs_target,coverage,origin,path_prefix,source_url,attribution FROM app.public_catalog_revisions WHERE id=:r RETURNING id"""), {'actor': actor, 'r': revision})
                source = await connection.scalar(text('INSERT INTO app.sources(collection_id,source_selection_id) VALUES(:c,:s) RETURNING id'), {'c': collection, 's': selection})
                _, version, _ = await _document(connection, store, collection, snapshot, generation, url=source_url, source=source)
                eligible = await connection.scalar(text('SELECT app.personal_assessment_eligible(:v)'), {'v': version})
                catalogs[key] = revision, collection, eligible
            revision, collection, eligible = catalogs[key]
            await connection.execute(text("INSERT INTO app.project_catalog_selections(project_id,dependency_id,catalog_revision_id,fallback_accepted) VALUES(:p,:dependency,:r,false)"),
                {'p': project, 'dependency': dependency['id'], 'r': revision})
            state['collection_ids'].append(str(collection))
            state['catalog_revision_ids'].append(str(revision))
            if not eligible:
                state['source_guardrail_blocked'].append(source_url)
        if case.kind == 'denied':
            await connection.execute(text("INSERT INTO app.project_processor_approvals(project_id,processor_id,approved_by) VALUES(:p,'test:offline-release:openai:v1',:actor)"), {'p': project, 'actor': owner})
            await connection.execute(text("INSERT INTO app.collection_processor_approvals(collection_id,processor_id,approved_by) VALUES(:c,'test:offline-release:openai:v1',:actor)"), {'c': default, 'actor': owner})
            private = parse_text(b'Synthetic other-owner private deployment instructions.', 'text/plain')
            _, version, chunks = await _document(connection, store, default, private, generation)
            turn = await connection.scalar(text("""INSERT INTO app.turns(conversation_id,sequence,idempotency_key,message,status,answer,citations)
                VALUES(:c,1,:key,'Earlier private question','completed','Synthetic retained private answer',CAST(:citations AS jsonb)) RETURNING id"""),
                {'c': conversation, 'key': uuid4(), 'citations': json.dumps([{'id': 'offline-private', 'chunk_id': str(chunks[0]),
                    'document_version_id': str(version), 'generation_id': str(generation), 'excerpt': private['text']}])})
            state['retained_turn_id'] = str(turn)
        setups[case.id] = state
    blocked = [case.id for case in dataset.cases if case.kind == 'answerable' and setups[case.id]['source_guardrail_blocked']]
    return {'dataset_sha256': dataset._sha256, 'sources_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
        'generation_id': str(generation), 'cases': setups, 'source_blocked_answer_cases': blocked,
        'all_answerable_cases_have_eligible_sources': not blocked, 'embedding_kind': 'synthetic_unit_vector',
        'provider_calls': 0, 'semantic_quality_evidence': False}
