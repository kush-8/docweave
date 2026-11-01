"""Default GitHub-only personal application; no SaaS domain routers are mounted."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
import os
from dotenv import dotenv_values
from uuid import UUID
from docweave.core.paths import ROOT
from docweave.api.errors import install_error_handlers
from docweave.api.middleware import install_middleware
from docweave.api.routes.github_auth import router as auth_router
from docweave.api.routes.personal import router as project_router
from docweave.api.routes.conversations import router as conversation_router
from docweave.api.routes.ingestion import router as ingestion_router
from docweave.api.routes.health import router as health_router
from docweave.api.routes.providers import router as provider_router
from docweave.core.github_settings import GitHubSettings
from docweave.core.settings import database_url
from docweave.db.engine import make_engine
from docweave.integrations.github import GitHubClient

def create_app(*,github_settings=None,auth_engine=None,github_client=None):
    settings=github_settings or GitHubSettings.load()
    engine=auth_engine or (make_engine(database_url('DATABASE_URL')) if settings else None)
    client=github_client or (GitHubClient(settings) if settings else None)
    @asynccontextmanager
    async def lifespan(app):
        yield
        if engine is not None and auth_engine is None:
            await engine.dispose()
    app=FastAPI(title='DocWeave API',version='0.2.0',description='Personal GitHub-linked documentation assistant.',lifespan=lifespan)
    app.state.github=(settings,engine,client) if settings else None
    app.state.runtime_config={**dotenv_values(ROOT / ".env"),**os.environ}
    install_middleware(app)
    install_error_handlers(app)
    for router in (auth_router,project_router,conversation_router,ingestion_router,provider_router,health_router):
        app.include_router(router)
    generate_openapi=app.openapi
    def openapi():
        schema=generate_openapi()
        public={'/api/v1/auth/login','/api/v1/auth/callback','/api/v1/providers','/api/v1/catalog','/api/v1/catalog/references','/api/v1/health/live','/api/v1/health/ready'}
        for path,methods in schema['paths'].items():
            for method,operation in methods.items():
                if method not in ('get','post','put','patch','delete'):
                    continue
                operation['security']=[] if path in public else [{'sessionCookie':[],**({'csrfToken':[]} if method!='get' else {})}]
        return schema
    app.openapi=openapi
    return app
