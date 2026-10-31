from authlib.integrations.starlette_client import OAuth


def make_oidc(settings, **client_kwargs):
    return OAuth().register("keycloak", client_id=settings.client_id, client_secret=settings.client_secret,
        server_metadata_url=settings.issuer + "/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256",
                       "timeout": 10, "trust_env": False, **client_kwargs})
