"""
QuickBooks Online connection: .env settings, OAuth sign-in, token refresh, API calls.
Standard library only, so nothing extra needs installing.
"""
import base64
import sys
import http.server
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".qbo"                      # logs, reports, ID map (git-ignored)
TOKENS = ROOT / ".qbo_tokens.json"        # OAuth tokens (git-ignored)
AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
API = {"sandbox": "https://sandbox-quickbooks.api.intuit.com",
       "production": "https://quickbooks.api.intuit.com"}
SCOPE = "com.intuit.quickbooks.accounting"
MINOR_VERSION = "75"


class QBOError(Exception):
    def __init__(self, msg, status=None, body=None):
        super().__init__(msg)
        self.status, self.body = status, body


def log(msg):
    WORK.mkdir(exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, file=sys.stderr, flush=True)   # stderr: stdout belongs to MCP
    with open(WORK / "loader.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_env():
    path = ROOT / ".env"
    if not path.exists():
        raise SystemExit("No .env file found in the repo folder. Copy .env.example to .env "
                         "and fill in your keys.")
    env = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    missing = [k for k in ("QBO_CLIENT_ID", "QBO_CLIENT_SECRET")
               if not env.get(k) or env[k].startswith("paste-")]
    if missing:
        raise SystemExit(f".env is missing values for: {', '.join(missing)}")
    env.setdefault("QBO_ENVIRONMENT", "sandbox")
    env.setdefault("QBO_REDIRECT_URI", "http://localhost:8765/callback")
    if env.get("QBO_REALM_ID", "").startswith("paste-"):
        env["QBO_REALM_ID"] = ""
    if env["QBO_ENVIRONMENT"] != "sandbox":
        raise SystemExit("This loader only runs against a sandbox company "
                         "(QBO_ENVIRONMENT=sandbox).")
    return env


class QBO:
    def __init__(self):
        self.env = load_env()
        self.tokens = json.loads(TOKENS.read_text()) if TOKENS.exists() else {}
        self.realm = self.tokens.get("realm_id") or self.env.get("QBO_REALM_ID")
        self._last_call = 0.0

    # ------------------------------------------------------------------ OAuth
    def _basic(self):
        raw = f"{self.env['QBO_CLIENT_ID']}:{self.env['QBO_CLIENT_SECRET']}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def _token_request(self, form):
        req = urllib.request.Request(
            TOKEN_URL, data=urllib.parse.urlencode(form).encode(), method="POST",
            headers={"Authorization": self._basic(), "Accept": "application/json",
                     "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise QBOError(f"Token request failed ({e.code}): {e.read().decode(errors='ignore')}",
                           e.code)
        data["obtained_at"] = time.time()
        return data

    def _save_tokens(self):
        TOKENS.write_text(json.dumps(self.tokens, indent=2))

    def sign_in(self):
        redirect = self.env["QBO_REDIRECT_URI"]
        u = urllib.parse.urlparse(redirect)
        state = secrets.token_urlsafe(16)
        result = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if urllib.parse.urlparse(self.path).path != u.path:
                    self.send_response(404)
                    self.end_headers()
                    return
                result.update({k: v[0] for k, v in q.items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h2>Connected to QuickBooks.</h2>"
                                 b"<p>You can close this tab and go back to PowerShell.</p>")

            def log_message(self, *a):
                pass

        server = http.server.HTTPServer((u.hostname, u.port or 80), Handler)
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()
        url = AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": self.env["QBO_CLIENT_ID"], "response_type": "code", "scope": SCOPE,
            "redirect_uri": redirect, "state": state})
        log("Opening your browser to sign in to QuickBooks. Pick the SANDBOX company.")
        print("If the browser doesn't open, paste this address into it:\n" + url,
              file=sys.stderr, flush=True)
        webbrowser.open(url)
        t.join(timeout=600)
        server.server_close()
        if result.get("state") != state or "code" not in result:
            raise SystemExit(f"Sign-in did not complete: {result.get('error', 'no response')}")
        data = self._token_request({"grant_type": "authorization_code", "code": result["code"],
                                    "redirect_uri": redirect})
        data["realm_id"] = result.get("realmId")
        want = self.env.get("QBO_REALM_ID")
        if want and data["realm_id"] != want:
            log(f"Note: you connected company {data['realm_id']}, but .env says {want}. "
                "Using the company you just connected.")
        self.tokens, self.realm = data, data["realm_id"]
        self._save_tokens()
        log(f"Signed in. Company (realm) ID {self.realm}.")

    def access_token(self):
        if not self.tokens:
            self.sign_in()
        age = time.time() - self.tokens.get("obtained_at", 0)
        if age > self.tokens.get("expires_in", 3600) - 300:
            data = self._token_request({"grant_type": "refresh_token",
                                        "refresh_token": self.tokens["refresh_token"]})
            data["realm_id"] = self.realm
            self.tokens = data
            self._save_tokens()
        return self.tokens["access_token"]

    # ------------------------------------------------------------------ API
    def request(self, method, path, body=None, params=None, retries=5):
        params = dict(params or {})
        params["minorversion"] = MINOR_VERSION
        if method == "POST":
            # same requestid on every retry, so QuickBooks never creates a record twice
            params.setdefault("requestid", secrets.token_hex(16))
        url = f"{API[self.env['QBO_ENVIRONMENT']]}/v3/company/{self.realm}/{path}?" + \
              urllib.parse.urlencode(params)
        for attempt in range(retries):
            wait = 0.13 - (time.time() - self._last_call)   # stay under 500 requests/minute
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()
            req = urllib.request.Request(
                url, method=method, data=json.dumps(body).encode() if body is not None else None,
                headers={"Authorization": f"Bearer {self.access_token()}",
                         "Accept": "application/json", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="ignore")
                if e.code == 401 and attempt == 0:
                    self.tokens["obtained_at"] = 0          # force a refresh
                    continue
                if e.code in (429, 500, 502, 503, 504):
                    delay = 2 ** attempt * 3
                    log(f"QuickBooks returned {e.code}; retrying in {delay}s")
                    time.sleep(delay)
                    continue
                raise QBOError(f"{method} {path} failed ({e.code}): {text[:3000]}", e.code, text)
            except (urllib.error.URLError, TimeoutError) as e:
                delay = 2 ** attempt * 3
                log(f"Network problem ({e}); retrying in {delay}s")
                time.sleep(delay)
        raise QBOError(f"{method} {path} failed after {retries} attempts")

    def query(self, sql):
        """Runs a query and pages through all results."""
        out, start = [], 1
        while True:
            res = self.request("GET", "query",
                               params={"query": f"{sql} STARTPOSITION {start} MAXRESULTS 1000"})
            qr = res.get("QueryResponse", {})
            rows = next((v for k, v in qr.items() if isinstance(v, list)), [])
            out += rows
            if len(rows) < 1000:
                return out
            start += 1000

    def create(self, entity, payload):
        return self.request("POST", entity.lower(), payload)[entity]

    def update(self, entity, payload):
        return self.request("POST", entity.lower(), payload)[entity]

    def batch(self, items):
        """items: list of (bId, operation, entity, payload). Returns {bId: (entity_obj, fault)}."""
        body = {"BatchItemRequest": [{"bId": b, "operation": op, entity: p}
                                     for b, op, entity, p in items]}
        res = self.request("POST", "batch", body)
        out = {}
        for r in res.get("BatchItemResponse", []):
            fault = r.get("Fault")
            obj = next((v for k, v in r.items() if k not in ("bId", "Fault") and
                        isinstance(v, dict)), None)
            out[r["bId"]] = (obj, fault)
        return out

    def report(self, name, params):
        return self.request("GET", f"reports/{name}", params=params)
