"""Remove orphan workspace/member/manual-policy RPCs, retaining their active data scopes."""
import ast
from pathlib import Path
import re
from alembic import op
import sqlalchemy as sa

revision = '0044_retire_product_rpcs'
down_revision = '0043_retire_manual_schema'
branch_labels = None
depends_on = None

FUNCTIONS = {
    'app.create_workspace': 'app.create_workspace(text)',
    'app.list_workspaces': 'app.list_workspaces(timestamptz,uuid,integer)',
    'app.list_members': 'app.list_members(timestamptz,uuid,integer)',
    'app.change_member': 'app.change_member(uuid,text)',
    'app.project_workspace': 'app.project_workspace(uuid)',
    'app.project_view': 'app.project_view(uuid)',
    'app.create_collection': 'app.create_collection(uuid,text)',
    'app.replace_collection_grants': 'app.replace_collection_grants(uuid,integer,jsonb)',
    'app.replace_processing_policy': 'app.replace_processing_policy(text,uuid,integer,jsonb)',
    'app.collection_grants': 'app.collection_grants(uuid)',
    'app.processing_policy': 'app.processing_policy(text,uuid)',
    'app.lock_workspace_owner': 'app.lock_workspace_owner()',
    'app.personal_assessment_view': 'app.personal_assessment_view(uuid)',
}


def originals():
    functions = {}
    for filename in ('0003_workspaces.py', '0004_memberships.py', '0005_projects.py', '0006_collection_policy.py', '0040_guardrail_lifecycle.py'):
        for node in ast.walk(ast.parse(Path(__file__).with_name(filename).read_text(encoding='utf-8'))):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            sql = node.value
            match = re.match(r'\s*CREATE (?:OR REPLACE )?FUNCTION (app\.\w+)\(', sql)
            if match and match[1] in FUNCTIONS:
                functions[match[1]] = sql
    if set(functions) != set(FUNCTIONS):
        raise ValueError('Historical RPC definitions are incomplete')
    # 0043 already removed this obsolete block; downgrade must restore the exact 0043 body.
    pattern = r"\n\s*IF previous_role='owner' AND \(p_role IS NULL OR p_role<>'owner'\) THEN\s+UPDATE app.invitations.*?END IF;"
    functions['app.change_member'], changed = re.subn(pattern, '', functions['app.change_member'], flags=re.S)
    if changed != 1:
        raise ValueError('Unexpected historical member definition')
    return functions


def upgrade():
    functions = originals()
    connection = op.get_bind()
    known = set()
    for name, signature in FUNCTIONS.items():
        row = connection.execute(sa.text('SELECT oid,prosrc FROM pg_proc WHERE oid=CAST(:name AS regprocedure)'), {'name': signature}).mappings().one()
        body = functions[name].split('AS $$', 1)[1].rsplit('$$', 1)[0]
        if body.strip() != row['prosrc'].strip():
            raise ValueError('Unexpected product RPC definition requires operator review')
        known.add(row['oid'])
    names = '|'.join(re.escape(name.removeprefix('app.')) for name in FUNCTIONS)
    calls = re.compile(r'\b(?:'+names+r')\s*\(', re.I)
    for oid, source in connection.execute(sa.text("""SELECT p.oid,p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE p.prokind IN ('f','p') AND n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema'""")):
        if oid not in known and calls.search(source.replace('"', '')):
            raise ValueError('Unknown SQL consumer requires review before RPC retirement')
    for signature in FUNCTIONS.values():
        op.execute('DROP FUNCTION '+signature)


def downgrade():
    functions = originals()
    for name, signature in reversed(tuple(FUNCTIONS.items())):
        op.execute(functions[name].replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1))
        op.execute('REVOKE ALL ON FUNCTION '+signature+' FROM PUBLIC,docweave_runtime')
        if name != 'app.lock_workspace_owner':
            op.execute('GRANT EXECUTE ON FUNCTION '+signature+' TO docweave_runtime')
