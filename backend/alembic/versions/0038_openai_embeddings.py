"""Admit OpenAI embeddings only, preserving immutable profiles and prior charges."""
import importlib.util
from pathlib import Path
from alembic import op

revision='0038_openai_embeddings'
down_revision='0037_private_source_states'
branch_labels=None
depends_on=None

def eligibility():
    spec=importlib.util.spec_from_file_location('openai_previous_roles',Path(__file__).with_name('0010_provider_roles.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.eligibility(True)

def constraints(providers):
    for table in ('processors','provider_profiles'):
        op.execute(f'ALTER TABLE app.{table} DROP CONSTRAINT ck_{table}_valid_provider')
        op.execute(f'ALTER TABLE app.{table} ADD CONSTRAINT ck_{table}_valid_provider CHECK (provider IN ({providers}))')

def upgrade():
    constraints("'gemini','groq','huggingface','openai'")
    op.execute(eligibility().replace("p.provider<>'gemini'","p.provider NOT IN ('gemini','openai')")
        .replace("pr.provider='gemini' AND pr.roles ? 'embedding'","pr.provider IN ('gemini','openai') AND pr.roles ? 'embedding'"))

def downgrade():
    # Refuse to discard or relabel retained OpenAI identity/financial history.
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM app.provider_profiles WHERE provider='openai')
        OR EXISTS(SELECT 1 FROM app.processors WHERE provider='openai') THEN
        RAISE EXCEPTION 'Preserve OpenAI profiles and accounting before downgrade'; END IF; END $$""")
    op.execute(eligibility())
    constraints("'gemini','groq','huggingface'")
