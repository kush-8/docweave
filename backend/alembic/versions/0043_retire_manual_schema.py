"""Retire empty invitation and manual documentation queues, preserving operator scopes."""
import ast
from pathlib import Path
import re
from alembic import op
import sqlalchemy as sa

revision = '0043_retire_manual_schema'
down_revision = '0042_deletion_receipts'
branch_labels = None
depends_on = None

TABLES = ('invitations', 'documentation_requests')
FUNCTIONS = {
    'app.create_invitation': 'app.create_invitation(text,text,text)',
    'app.list_invitations': 'app.list_invitations(timestamptz,uuid,integer)',
    'app.revoke_invitation': 'app.revoke_invitation(uuid)',
    'app.accept_invitation': 'app.accept_invitation(text)',
    'app.create_project': 'app.create_project(jsonb)',
    'app.update_project': 'app.update_project(uuid,integer,jsonb)',
    'app.replace_project_documentation': 'app.replace_project_documentation(uuid)',
}
MEMBER = 'app.change_member(uuid,text)'


def originals():
    # Reuse only the named immutable historical definitions so downgrade does not recreate unrelated structures.
    tables, functions = {}, {}
    for filename in ('0004_memberships.py', '0005_projects.py'):
        tree = ast.parse(Path(__file__).with_name(filename).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if (not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute)
                or not isinstance(node.func.value, ast.Name) or node.func.value.id != 'op'
                or not node.args or not isinstance(node.args[0], ast.Constant)):
                continue
            value = node.args[0].value
            if node.func.attr == 'create_table' and value in TABLES:
                tables[value] = node
            elif node.func.attr == 'execute' and isinstance(value, str):
                match = re.match(r'\s*CREATE FUNCTION (app\.\w+)\(', value)
                if match and match[1] in {*FUNCTIONS, 'app.change_member'}:
                    functions[match[1]] = value
    if set(tables) != set(TABLES) or set(functions) != {*FUNCTIONS, 'app.change_member'}:
        raise ValueError('Historical retirement definitions are incomplete')
    return tables, functions


def upgrade():
    _, functions = originals()
    connection = op.get_bind()
    op.execute('LOCK TABLE app.invitations,app.documentation_requests IN ACCESS EXCLUSIVE MODE')
    for table in TABLES:
        if connection.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM app.'+table+')')):
            raise ValueError('Legacy records require explicit operator preservation before retirement')
    known = {}
    for name, signature in {**FUNCTIONS, 'app.change_member': MEMBER}.items():
        row = connection.execute(sa.text('SELECT oid,prosrc,pg_get_functiondef(oid) definition FROM pg_proc WHERE oid=CAST(:name AS regprocedure)'), {'name': signature}).mappings().one()
        body = functions[name].split('AS $$', 1)[1].rsplit('$$', 1)[0]
        if body.strip() != row['prosrc'].strip():
            raise ValueError('Unexpected legacy function definition requires operator review')
        known[row['oid']] = row
    names = '|'.join(re.escape(name) for name in (*TABLES, *(name.removeprefix('app.') for name in FUNCTIONS)))
    references = re.compile(r'\b(?:'+names+r')\b', re.I)
    for oid, source in connection.execute(sa.text("""SELECT p.oid,p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE p.prokind IN ('f','p') AND n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema'""")):
        if oid not in known and references.search(source.replace('"', '')):
            raise ValueError('Unknown SQL consumer requires review before retirement')
    definition = next(row['definition'] for row in known.values() if 'FUNCTION app.change_member(' in row['definition'])
    pattern = r"\n\s*IF previous_role='owner' AND \(p_role IS NULL OR p_role<>'owner'\) THEN\s+UPDATE app.invitations.*?END IF;"
    definition, changed = re.subn(pattern, '', definition, flags=re.S)
    if changed != 1:
        raise ValueError('Unexpected invitation revocation dependency')
    op.execute(definition)
    for signature in FUNCTIONS.values():
        op.execute('DROP FUNCTION '+signature)
    for table in TABLES:
        op.drop_table(table, schema='app')


def downgrade():
    tables, functions = originals()
    for name in TABLES:
        expression = ast.fix_missing_locations(ast.Expression(tables[name]))
        eval(compile(expression, '<historical retirement table>', 'eval'), {'op': op, 'sa': sa, '__builtins__': {}})
        op.execute('ALTER TABLE app.'+name+' ENABLE ROW LEVEL SECURITY')
        op.execute('REVOKE ALL ON app.'+name+' FROM PUBLIC,docweave_runtime')
    for sql in functions.values():
        op.execute(sql.replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1))
    for name, signature in FUNCTIONS.items():
        op.execute('REVOKE ALL ON FUNCTION '+signature+' FROM PUBLIC,docweave_runtime')
        if name != 'app.replace_project_documentation':
            op.execute('GRANT EXECUTE ON FUNCTION '+signature+' TO docweave_runtime')
