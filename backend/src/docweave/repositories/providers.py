from sqlalchemy import text


async def list_profiles(connection, values):
    return await connection.execute(text("""
            SELECT p.id,p.created_at,p.provider,p.model,p.backend,app.profile_disabled_reason(p.id) AS disabled_reason,
                app.profile_disabled_reason(p.id) IS NULL AS enabled,
                coalesce((SELECT jsonb_agg(jsonb_build_object('id',pr.id,'provider',pr.provider,'backend',pr.backend,'roles',pr.roles) ORDER BY pr.id)
                    FROM app.processors pr WHERE p.processor_ids ? pr.id),'[]'::jsonb) AS processors
            FROM app.provider_profiles p WHERE p.role='generation' AND (CAST(:after AS timestamptz) IS NULL OR (p.created_at,p.id)>(:after,:id))
            ORDER BY p.created_at,p.id LIMIT :limit
        """), values)
