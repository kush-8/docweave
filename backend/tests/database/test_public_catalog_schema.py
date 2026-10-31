"""Public catalog schema foundation, on guarded disposable PostgreSQL only."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.database.test_database import A, B, PA, PB, WA
from tests.database.test_database import databases, test_urls  # noqa: F401


def test_public_catalog_models_have_explicit_parents_and_nullable_public_scope():
    from docweave.db.models import Base
    for table in ('sources', 'documents', 'document_versions', 'ingestion_jobs', 'document_indexes', 'chunks'):
        assert Base.metadata.tables['app.' + table].c.workspace_id.nullable
    assert Base.metadata.tables['app.chunks'].c.project_id.nullable
    assert Base.metadata.tables['app.collections'].c.catalog_revision_id.nullable
    assert Base.metadata.tables['app.documentation_selections'].c.catalog_revision_id.nullable
    assert Base.metadata.tables['app.public_catalog_revisions'].c.enabled.server_default is not None


async def add_revision(connection, *, enabled=False, approved=False):
    return await connection.scalar(text("""INSERT INTO app.public_catalog_revisions
        (technology,ecosystem,docs_target,coverage,origin,path_prefix,source_url,attribution,source_hash,enabled,source_approved)
        VALUES ('react','javascript','19.1.0','{"granularity":"exact","version":"19.1.0"}',
            'https://react.dev','/','https://react.dev/reference','React',:hash,:enabled,:approved) RETURNING id"""),
        {'hash': 'a' * 64, 'enabled': enabled, 'approved': approved})


@pytest.mark.anyio
async def test_catalog_definitions_are_operator_only_immutable_and_revocable(databases):
    owner, runtime = databases
    async with owner.begin() as connection:
        hidden = await add_revision(connection)
        public = await add_revision(connection, enabled=True, approved=True)
    async with runtime.connect() as connection:
        assert (await connection.execute(text('SELECT id FROM app.public_catalog_revisions'))).scalars().all() == [public]
    for statement in (
        "UPDATE app.public_catalog_revisions SET docs_target='20' WHERE id=:id",
        "UPDATE app.public_catalog_revisions SET enabled=true WHERE id=:id",
        "DELETE FROM app.public_catalog_revisions WHERE id=:id",
    ):
        with pytest.raises(DBAPIError):
            async with owner.begin() as connection:
                await connection.execute(text(statement), {'id': hidden})
    with pytest.raises(DBAPIError):
        async with runtime.begin() as connection:
            await add_revision(connection)
    async with owner.begin() as connection:
        await connection.execute(text('UPDATE app.public_catalog_revisions SET enabled=false WHERE id=:id'), {'id': public})
    async with runtime.connect() as connection:
        assert (await connection.execute(text('SELECT id FROM app.public_catalog_revisions'))).scalars().all() == []


@pytest.mark.anyio
async def test_public_collection_has_one_parent_and_selections_are_owner_private(databases):
    owner, runtime = databases
    async with owner.begin() as connection:
        revision = await add_revision(connection, enabled=True, approved=True)
        collection = await connection.scalar(text("INSERT INTO app.collections(catalog_revision_id,name) VALUES (:r,'Public React') RETURNING id"), {'r': revision})
        await connection.execute(text('UPDATE app.projects SET owner_user_id=:owner WHERE id=:project'), {'owner': A, 'project': PA})
        await connection.execute(text("INSERT INTO app.project_catalog_selections(project_id,dependency_id,catalog_revision_id) VALUES (:p,'react',:r)"), {'p': PA, 'r': revision})
    with pytest.raises(DBAPIError):
        async with owner.begin() as connection:
            await connection.execute(text("INSERT INTO app.collections(project_id,workspace_id,catalog_revision_id,name) VALUES (:p,:w,:r,'Invalid')"), {'p': PA, 'w': WA, 'r': revision})
    for actor, count in ((A, 1), (B, 0)):
        async with runtime.begin() as connection:
            await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"), {'actor': str(actor)})
            assert await connection.scalar(text('SELECT count(*) FROM app.project_catalog_selections')) == count
            assert await connection.scalar(text('SELECT count(*) FROM app.collections WHERE id=:c'), {'c': collection}) == 0


@pytest.mark.anyio
async def test_public_source_and_document_cannot_reference_private_scope(databases):
    owner, _ = databases
    async with owner.begin() as connection:
        revision = await add_revision(connection, enabled=True, approved=True)
        public_collection = await connection.scalar(text("INSERT INTO app.collections(catalog_revision_id,name) VALUES (:r,'Public') RETURNING id"), {'r': revision})
        selection = await connection.scalar(text("""INSERT INTO app.documentation_selections
            (catalog_revision_id,approved_by,technology,docs_target,coverage,source_url,origin,path_prefix,attribution)
            SELECT id,:actor,technology,docs_target,coverage,source_url,origin,path_prefix,attribution
            FROM app.public_catalog_revisions WHERE id=:r RETURNING id"""), {'actor': A, 'r': revision})
        source = await connection.scalar(text('INSERT INTO app.sources(collection_id,source_selection_id) VALUES (:c,:s) RETURNING id'), {'c': public_collection, 's': selection})
        private_collection = await connection.scalar(text('SELECT id FROM app.collections WHERE project_id=:p'), {'p': PA})
    invalids = [
        ("INSERT INTO app.documents(workspace_id,collection_id,source_id,title,media_type) VALUES (:w,:c,:s,'Private','text/plain')", {'w': WA, 'c': private_collection, 's': source}),
        ("INSERT INTO app.sources(workspace_id,collection_id,source_selection_id) VALUES (:w,:c,:s)", {'w': WA, 'c': private_collection, 's': selection}),
        ("INSERT INTO app.documents(collection_id,title,media_type) VALUES (:c,'Missing collection','text/plain')", {'c': PB}),
    ]
    for statement, params in invalids:
        with pytest.raises(DBAPIError):
            async with owner.begin() as connection:
                await connection.execute(text(statement), params)
    async with owner.begin() as connection:
        document = await connection.scalar(text("INSERT INTO app.documents(collection_id,source_id,title,media_type) VALUES (:c,:s,'Public','text/plain') RETURNING id"), {'c': public_collection, 's': source})
        assert document is not None
