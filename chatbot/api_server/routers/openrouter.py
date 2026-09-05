"""Browser connection to OpenRouter with a one-time owner link and S256 PKCE."""

from html import escape

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

COOKIE = "ratichat_owner"
HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; connect-src 'self'; form-action 'self' https://openrouter.ai; frame-ancestors 'none'; base-uri 'none'",
}


def page(body, status=200):
    return HTMLResponse("""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RATi Chat · Connect OpenRouter</title>
<style>
:root{color-scheme:dark;font-family:ui-sans-serif,system-ui,sans-serif;background:#15130f;color:#f8f3e7}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:28px}
main{width:100%;max-width:500px}header{letter-spacing:.16em;font-size:13px;color:#f0b94e;margin-bottom:72px}
h1{font-size:clamp(32px,7vw,44px);line-height:1.1;letter-spacing:-.04em;margin:0 0 24px}
p{font-size:17px;line-height:1.6;color:#c9c0af}small{display:block;line-height:1.6;color:#a59b87;margin-top:24px}
button,.button{display:block;width:100%;text-align:center;background:#efb64a;border:0;border-radius:10px;padding:17px 22px;margin-top:32px;color:#241b09;font:650 17px ui-sans-serif,system-ui;cursor:pointer;text-decoration:none}
a{color:#efb64a}footer{margin-top:64px;font-size:13px;color:#887f6e}#notice{min-height:1.6em}
</style><main><header>RATi / CHAT</header>""" + body + """
<footer>Your account. Your community.</footer></main></html>""", status_code=status, headers=HEADERS)


def create_router(orchestrator):
    router = APIRouter()
    link = orchestrator.openrouter_link

    @router.post("/api/ai/openrouter/link")
    async def owner_link():
        try:
            return JSONResponse({"url": link.issue_link(), "expires_in": 900}, headers=HEADERS)
        except ValueError as error:
            return JSONResponse({"detail": str(error)}, status_code=503, headers=HEADERS)

    @router.get("/connect/openrouter")
    async def connect(request: Request):
        owner = link.session(request.cookies.get(COOKIE))
        if owner:
            linked_key = link.api_key()
            title = "OpenRouter is connected" if linked_key else "Give RATi a voice."
            description = "RATi can use your linked OpenRouter key for chat replies." if linked_key else "Link your OpenRouter account to power RATi Chat. You choose the key and its spending limit on OpenRouter."
            label = "Connect another key" if linked_key else "Connect OpenRouter"
            extra = ('<p><a href="https://openrouter.ai/keys/' + link.digest(linked_key) + '">Manage this key on OpenRouter</a></p><a href="https://chat.rati.chat">Open RATi Chat →</a>') if linked_key else ""
            return page(f'<h1>{title}</h1><p>{description}</p>{extra}<form method="post" action="/connect/openrouter/start"><input type="hidden" name="csrf" value="{escape(owner["csrf"])}"><button>{label}</button></form><small>Messages in RATi’s rooms are sent to OpenRouter and the selected model provider so RATi can reply. The linked key is stored encrypted on the bot server.</small>')
        return page('<h1>Give RATi a voice.</h1><p>Connect your OpenRouter account to power RATi Chat.</p><p id="notice" role="status">Open your owner link to begin.</p><script src="/connect/openrouter/setup.js" defer></script>')

    @router.get("/connect/openrouter/setup.js")
    async def setup_script():
        return Response("""(async()=>{const ticket=location.hash.slice(1);history.replaceState(null,'',location.pathname);if(!ticket)return;const notice=document.querySelector('#notice');notice.textContent='Opening your connection…';try{const response=await fetch('/connect/openrouter/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket})});if(response.ok){location.reload();return;}notice.textContent='This owner link has expired. Open a fresh link to continue.';}catch{notice.textContent='Please try your owner link again.'}})();""", media_type="application/javascript", headers=HEADERS)

    @router.post("/connect/openrouter/session")
    async def session(request: Request):
        if request.headers.get("origin") != link.public_url:
            return JSONResponse({"detail": "Open this page on the RATi server."}, status_code=403, headers=HEADERS)
        try:
            body = await request.json()
            ticket = body.get("ticket", "")
            if not isinstance(ticket, str) or len(ticket) > 128:
                raise ValueError("Open a fresh owner link.")
            token = link.open_session(ticket)
        except (ValueError, AttributeError):
            return JSONResponse({"detail": "Open a fresh owner link."}, status_code=401, headers=HEADERS)
        response = JSONResponse({"ready": True}, headers=HEADERS)
        response.set_cookie(COOKIE, token, max_age=1800, path="/connect/openrouter", secure=True, httponly=True, samesite="lax")
        return response

    @router.post("/connect/openrouter/start")
    async def start(request: Request):
        form = await request.form()
        try:
            url = link.start(request.cookies.get(COOKIE), str(form.get("csrf", "")))
            return RedirectResponse(url, status_code=303, headers=HEADERS)
        except ValueError as error:
            return page(f'<h1>Open a fresh owner link.</h1><p>{escape(str(error))}</p>', 401)

    @router.get("/connect/openrouter/callback/{flow}")
    async def callback(flow: str, request: Request):
        try:
            verifier = link.consume_flow(flow, request.cookies.get(COOKIE))
            code = request.query_params.get("code", "")
            if not code or len(code) > 2048:
                raise ValueError("Return to Connect OpenRouter and approve a key.")
            async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
                result = await client.post("https://openrouter.ai/api/v1/auth/keys", json={"code": code, "code_verifier": verifier, "code_challenge_method": "S256"})
                result.raise_for_status()
                key = result.json().get("key")
            link.save_key(key)
            orchestrator.ai_engine.api_key = key
            return RedirectResponse("/connect/openrouter", status_code=303, headers=HEADERS)
        except (ValueError, httpx.HTTPError):
            return page('<h1>Try connecting again.</h1><p>Your connection could not be completed. Return to the connection page to start a fresh request.</p><a class="button" href="/connect/openrouter">Connect OpenRouter</a>', 400)

    return router
