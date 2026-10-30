"""Reconcile admission to Gemini embeddings and Groq LLM roles, retaining history."""

from alembic import op

revision = "0010_provider_roles"
down_revision = "0009_retrieval"
branch_labels = None
depends_on = None


def eligibility(selected_pipeline):
    provider_rule = """WHEN (p.role='embedding' AND p.provider<>'gemini')
        OR (p.role<>'embedding' AND p.provider<>'groq') THEN 'provider_unavailable'""" if selected_pipeline else ""
    reranking = "groq" if selected_pipeline else "gemini"
    return f"""
        CREATE OR REPLACE FUNCTION app.profile_disabled_reason(p_profile uuid) RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
            SELECT CASE WHEN NOT p.enabled THEN 'disabled'
                {provider_rule}
                WHEN NOT p.pricing_verified OR p.input_usd_per_million IS NULL OR p.output_usd_per_million IS NULL OR p.fixed_usd IS NULL THEN 'pricing_unavailable'
                WHEN NOT p.capabilities_verified OR p.max_input_tokens IS NULL OR p.max_output_tokens IS NULL THEN 'capability_unverified'
                WHEN NOT p.account_verified THEN 'account_unverified'
                WHEN jsonb_array_length(p.processor_ids)=0 OR EXISTS (SELECT 1 FROM jsonb_array_elements(p.processor_ids) v WHERE jsonb_typeof(v)<>'string')
                    OR (SELECT count(DISTINCT v) FROM jsonb_array_elements_text(p.processor_ids) v)<>jsonb_array_length(p.processor_ids)
                    OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(p.processor_ids) v(id) LEFT JOIN app.processors pr ON pr.id=v.id WHERE pr.id IS NULL OR NOT pr.enabled)
                    OR NOT EXISTS (SELECT 1 FROM app.processors pr WHERE p.processor_ids ? pr.id AND pr.provider=p.provider AND pr.backend=p.backend AND pr.roles ? p.role)
                    OR (p.role='generation' AND (NOT EXISTS (SELECT 1 FROM app.processors pr WHERE p.processor_ids ? pr.id AND pr.provider='gemini' AND pr.roles ? 'embedding')
                        OR NOT EXISTS (SELECT 1 FROM app.processors pr WHERE p.processor_ids ? pr.id AND pr.provider='{reranking}' AND pr.roles ? 'reranking'))) THEN 'processor_unavailable'
                ELSE NULL END FROM app.provider_profiles p WHERE p.id=p_profile
        $$
    """


def upgrade():
    op.execute(eligibility(True))


def downgrade():
    op.execute(eligibility(False))
