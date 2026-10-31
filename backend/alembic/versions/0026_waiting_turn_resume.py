"""Persist dependency resolution across source waits; do not repeat hosted work."""
from alembic import op
import importlib.util
from pathlib import Path
revision='0026_waiting_turn_resume'
down_revision='0025_personal_guardrail_review'
branch_labels=None
depends_on=None

def prior(name):
 spec=importlib.util.spec_from_file_location('prior_'+name,Path(__file__).with_name(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def upgrade():
 turn=prior('0022_personal_release').prior('0016_personal_conversations').FUNCTIONS['app.personal_turn(uuid)'].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
 turn=turn.replace("'progress',t.progress", "'progress',t.progress,'required_dependencies',t.required_dependencies")
 turn=turn.replace("'message',t.message,'status',t.status,'answer',t.answer,'citations',t.citations", "'message',CASE WHEN app.personal_citations_current(c.project_id,t.citations) THEN t.message ELSE '' END,'status',CASE WHEN app.personal_citations_current(c.project_id,t.citations) THEN t.status ELSE 'blocked_policy' END,'answer',CASE WHEN app.personal_citations_current(c.project_id,t.citations) THEN t.answer ELSE NULL END,'citations',CASE WHEN app.personal_citations_current(c.project_id,t.citations) THEN t.citations ELSE '[]'::jsonb END")
 op.execute(turn)
 claim=prior('0016_personal_conversations').FUNCTIONS['app.personal_claim_job(uuid)'].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1).replace("context_revision=project.context_revision,progress", "context_revision=CASE WHEN status='waiting_for_sources' THEN context_revision ELSE project.context_revision END,progress")
 op.execute(claim)
 context=prior('0018_personal_job_context').FUNCTIONS['app.personal_job_context(uuid,uuid)'].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1).replace('WHERE id=j.turn_id; END IF;',"WHERE id=j.turn_id AND required_dependencies='[]'::jsonb; END IF;")
 op.execute(context)

def downgrade():
 for name,signature in (('0016_personal_conversations','app.personal_claim_job(uuid)'),('0018_personal_job_context','app.personal_job_context(uuid,uuid)')):
  op.execute(prior(name).FUNCTIONS[signature].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
 # Keep the safe release view; dropping the additional JSON response field is unnecessary.
