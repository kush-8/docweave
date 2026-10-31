"""Auth persistence; callers own transactions and connection lifetimes."""

from sqlalchemy import text


async def session_user(connection, values):
    return await connection.execute(text(
            "SELECT user_id FROM app.auth_sessions WHERE token_hash=:hash AND expires_at>now()"
        ), values)


async def set_actor(connection, values):
    return await connection.execute(text("SELECT set_config('docweave.actor_id',:actor,true)"), values)


async def load_user(connection, values):
    return await connection.execute(text("SELECT id,display_name,email,email_verified FROM app.users WHERE id=:id"), values)


async def expire_login_limits(connection):
    return await connection.execute(text("DELETE FROM app.auth_rate_limits WHERE resets_at<=now()"))


async def record_login_attempt(connection, values):
    return await connection.scalar(text("""
            INSERT INTO app.auth_rate_limits(bucket,attempts,resets_at) VALUES (:bucket,1,now()+interval '60 seconds')
            ON CONFLICT (bucket) DO UPDATE SET attempts=app.auth_rate_limits.attempts+1 RETURNING attempts
        """), values)


async def expire_flows(connection):
    return await connection.execute(text("DELETE FROM app.auth_flows WHERE expires_at<=now()"))


async def expire_sessions(connection):
    return await connection.execute(text("DELETE FROM app.auth_sessions WHERE expires_at<=now()"))


async def delete_browser_flow(connection, values):
    return await connection.execute(text("DELETE FROM app.auth_flows WHERE browser_hash=:browser"), values)


async def create_flow(connection, values):
    return await connection.execute(text("""
            INSERT INTO app.auth_flows(state_hash,browser_hash,encrypted_data,expires_at)
            VALUES (:state,:browser,:data,now()+interval '10 minutes')
        """), values)


async def consume_flow(connection, values):
    return await connection.scalar(text("""
            DELETE FROM app.auth_flows WHERE state_hash=:state AND browser_hash=:browser AND expires_at>now()
            RETURNING encrypted_data
        """), values)


async def provision_identity(connection, values):
    return await connection.scalar(text("SELECT app.provision_identity(:issuer,:subject,:name,:email)"), values)


async def delete_session(connection, values):
    return await connection.execute(text("DELETE FROM app.auth_sessions WHERE token_hash=:hash"), values)


async def create_session(connection, values):
    return await connection.execute(text("""
            INSERT INTO app.auth_sessions(token_hash,user_id,encrypted_token,expires_at) VALUES (:hash,:user,:token,:expiry)
        """), values)
