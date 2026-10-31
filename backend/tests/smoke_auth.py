"""Explicit local-only smoke: pytest backend/tests/smoke_auth.py -q.

Not collected by the default suite. Creates a synthetic identity in local Keycloak;
uses only captured SMTP and the guarded disposable application database.
"""

import asyncio
import re
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest

from test_database import databases
from test_database import test_urls  # noqa: F401


class Forms(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.forms, self.links = [], []
        self.current = None
        self.visible = []
        self.suppressed = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self.suppressed = True
        if tag == "form":
            self.current = {"action": attrs.get("action", ""), "fields": {}}
            self.forms.append(self.current)
        elif tag == "input" and self.current is not None and "name" in attrs and "disabled" not in attrs:
            self.current["fields"][attrs["name"]] = attrs.get("value", "")
        elif tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None
        if tag in ("script", "style"):
            self.suppressed = False

    def handle_data(self, data):
        if not self.suppressed and data.strip():
            self.visible.append(data.strip())


def test_form_parser_preserves_hidden_fields_and_decodes_actions():
    page = Forms('<form action="/submit?a=1&amp;b=2"><input name="hidden" value="saved"><input name="off" disabled></form>')
    assert page.forms == [{"action": "/submit?a=1&b=2", "fields": {"hidden": "saved"}}]


@pytest.mark.anyio
async def test_local_email_registration_verification_reset_and_backend_session(databases):
    from docweave.core.settings import AuthSettings
    from docweave.main import create_app

    settings = AuthSettings.load()
    assert settings and settings.issuer == "http://127.0.0.1:58080/realms/docweave", "Smoke requires the local test realm"
    assert settings.origin == "http://127.0.0.1:58000", "Smoke requires the exact local callback"
    _, runtime = databases
    app = create_app(auth_settings=settings, auth_engine=runtime)
    email = f"backend-smoke-{uuid4().hex}@example.test"
    password, replacement = "Test-only-" + uuid4().hex, "Replacement-" + uuid4().hex

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=settings.origin) as api, \
            httpx.AsyncClient(timeout=15, trust_env=False) as identity:
        async def identity_request(url, fields=None):
            response = await identity.request("POST" if fields is not None else "GET", url, data=fields)
            # shortcut: emulate Chrome's verified loopback Secure-cookie exception; use HTTPS for deployed smoke tests.
            for cookie in identity.cookies.jar:
                if cookie.domain == "127.0.0.1":
                    cookie.secure = False
            return response

        async def navigate(url, fields=None):
            response = await identity_request(url, fields)
            for _ in range(12):
                if response.status_code not in (302, 303, 307, 308):
                    return response
                target = urljoin(str(response.url), response.headers["location"])
                if target.startswith(settings.callback + "?"):
                    return await api.get(target)
                assert target.startswith("http://127.0.0.1:58080/"), "Unexpected redirect outside local identity service"
                response = await identity_request(target)
            raise AssertionError("Identity redirect loop")

        async def submit(response, **fields):
            forms = Forms(response.text).forms
            if not forms:
                title = re.search(r"<title>(.*?)</title>", response.text, re.S)
                visible = " ".join(Forms(response.text).visible)
                cookies = [(c.name, c.secure, c.path) for c in identity.cookies.jar]
                raise AssertionError(f"Identity response has no form: {response.status_code}, title={title.group(1).strip() if title else 'none'}, text={visible[:350]}, cookie_flags={cookies}")
            form = forms[0]
            return await navigate(urljoin(str(response.url), form["action"]), {**form["fields"], **fields})

        async def mail_link(subject):
            for _ in range(20):
                messages = (await identity.get("http://127.0.0.1:8025/api/v1/messages")).json()["messages"]
                match = next((m for m in messages if subject in m["Subject"].lower()
                    and any(recipient["Address"] == email for recipient in m["To"])), None)
                if match:
                    message = (await identity.get("http://127.0.0.1:8025/api/v1/message/" + match["ID"])).json()
                    link = re.search(r"http://127\.0\.0\.1:58080/realms/docweave/login-actions/action-token\?[^\s<>]+", message["Text"])
                    assert link, "Captured email has no local action link"
                    return link.group()
                await asyncio.sleep(0.5)
            raise AssertionError("Local SMTP did not capture the expected email")

        async def start():
            response = await api.get("/api/v1/auth/login?method=email")
            assert response.status_code == 302, "Backend did not start OIDC login"
            return await navigate(response.headers["location"])

        login_page = await start()
        registration = next(link for link in Forms(login_page.text).links if "/registration?" in link)
        register_page = await navigate(urljoin(str(login_page.url), registration))
        registration_fields = Forms(register_page.text).forms[0]["fields"]
        password_field = "password-new" if "password-new" in registration_fields else "password"
        verify_page = await submit(register_page, email=email, firstName="Backend", lastName="Smoke",
            **{password_field: password, "password-confirm": password})
        assert verify_page.status_code == 200
        callback = await navigate(await mail_link("verif"))
        activation = Forms(callback.text).forms
        if callback.status_code == 200 and activation and "password-new" in activation[0]["fields"]:
            callback = await submit(callback, **{"password-new": password, "password-confirm": password})
        assert callback.status_code == 302, "Verification did not complete the backend callback: " + " ".join(Forms(callback.text).visible)[:400]
        me = await api.get("/api/v1/me")
        assert me.status_code == 200
        assert me.json()["verified_email"] == email
        old_cookie = api.cookies["docweave_session"]
        assert (await api.post("/api/v1/auth/logout", headers={"Origin": settings.origin,
            "X-CSRF-Token": me.json()["csrf_token"]})).status_code == 204
        assert (await api.get("/api/v1/me", headers={"Cookie": "docweave_session=" + old_cookie})).status_code == 401

        login_page = await start()
        reset = next(link for link in Forms(login_page.text).links if "/reset-credentials?" in link)
        reset_page = await navigate(urljoin(str(login_page.url), reset))
        await submit(reset_page, username=email)
        password_page = await navigate(await mail_link("reset"))
        callback = await submit(password_page, **{"password-new": replacement, "password-confirm": replacement})
        assert callback.status_code == 302, "Password reset did not complete the backend callback"
        me = await api.get("/api/v1/me")
        assert me.status_code == 200 and me.json()["verified_email"] == email
        assert (await api.post("/api/v1/auth/logout", headers={"Origin": settings.origin,
            "X-CSRF-Token": me.json()["csrf_token"]})).status_code == 204
