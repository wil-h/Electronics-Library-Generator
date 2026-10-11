import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_THIS_DIR, 'lib')
for p in (_THIS_DIR, _LIB_DIR):
    if p not in sys.path:
        sys.path.append(p)

import requests

try:
    import adsk.core
    _IN_FUSION = True
except ImportError:
    _IN_FUSION = False

# ---------------- internals: cert persistence ----------------

def _load_cert(self):
    if os.path.exists(self._cert_file):
        with open(self._cert_file, "r") as f:
            cert = json.load(f)
        # Guard against reusing a cert that's already used up or whose
        # 24h TTL has passed since the last time this ran.
        if cert.get("remaining_uses", 0) > 0 and cert.get("expires_at", 0) > time.time():
            return cert
    return None

def _save_cert(self):
    with open(self._cert_file, "w") as f:
        json.dump(self._cert, f)

def _clear_cert(self):
    self._cert = None
    if os.path.exists(self._cert_file):
        os.remove(self._cert_file)


class MouserClient:
    _REDIRECT_PORT = 8734
    _REDIRECT_URI = f"http://localhost:{_REDIRECT_PORT}/callback"
    api_base = "https://161c1k80d1.execute-api.us-east-1.amazonaws.com".rstrip("/")
    aps_client_id = "kiYr4eO7tyAAmFnYkYvW46djRPp0jAhNGpQjtYlK5N4YF2vp"

    def __init__(self, session_file=None, cert_file=None):
        self._session_file = session_file or os.path.join(
            os.path.dirname(__file__), "session.json"
        )
        self._cert_file = cert_file or os.path.join(
            os.path.dirname(__file__), "cert.json"
        )
        # {"cert_id": ..., "remaining_uses": ..., "expires_at": ...}
        # Loaded from disk so it survives across add-in invocations instead
        # of minting a fresh (quota-consuming) cert on every single call.
        self._cert = _load_cert(self)

    # ---------------- public API ----------------

    def login(self):
        """Call once at add-in startup. Opens a browser tab only the first
        time, or after 15+ days of inactivity. Silent otherwise."""
        if not self._load_session_token():
            self._run_oauth_flow()

    def is_logged_in(self):
        return self._load_session_token() is not None

    def logout(self):
        """Wipes the local session so the next call re-triggers login."""
        if os.path.exists(self._session_file):
            os.remove(self._session_file)
        self._clear_cert()

    def search_part(self, mouser_part_number):
        """Example call through the proxy. Swap the payload shape for
        whatever your real API actually expects."""
        return self.call({"part_number": mouser_part_number})

    def call(self, payload):
        """Generic entry point: sends payload through your proxy, handling
        cert issuance/renewal transparently. Use this directly if you have
        more than one type of request to make."""
        if not self._cert or self._cert.get("remaining_uses", 0) <= 0:
            self._issue_new_cert()

        resp = requests.post(
            f"{self.api_base}/proxy",
            headers={"X-Cert-Id": self._cert["cert_id"]},
            json=payload,
            timeout=30,
        )

        # Only re-issue when the SERVER says the cert itself is the problem.
        # 401 = missing/invalid cert. 429 + cert_exhausted_or_expired = used
        # up or past its 24h TTL. Any other error (502 upstream failure, 500
        # internal, 404 part not found, etc.) means the cert is still fine --
        # retrying with a new one won't fix it and just burns your daily quota.
        if resp.status_code == 401 or self._is_cert_exhausted(resp):
            self._issue_new_cert()
            resp = requests.post(
                f"{self.api_base}/proxy",
                headers={"X-Cert-Id": self._cert["cert_id"]},
                json=payload,
                timeout=30,
            )

        if resp.status_code < 300:
            self._cert["remaining_uses"] -= 1
            _save_cert(self)

        if resp.status_code == 500:
            return self.call(payload)
        resp.raise_for_status()
        return resp.json()

    def _is_cert_exhausted(self, resp):
        if resp.status_code != 429:
            return False
        try:
            return resp.json().get("error") == "cert_exhausted_or_expired"
        except ValueError:
            return False

    # ---------------- internals: session persistence ----------------

    def _load_session_token(self):
        if os.path.exists(self._session_file):
            with open(self._session_file, "r") as f:
                return json.load(f).get("session_token")
        return None

    def _save_session_token(self, session_token):
        with open(self._session_file, "w") as f:
            json.dump({"session_token": session_token}, f)

    # ---------------- internals: PKCE + OAuth ----------------

    @staticmethod
    def _generate_pkce_pair():
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        return verifier, challenge

    class _CallbackHandler(http.server.BaseHTTPRequestHandler):
        auth_code = None

        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in params:
                MouserClient._CallbackHandler.auth_code = params["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<html><body>Success, you can close this tab.</body></html>")
            else:
                self.send_response(400)
                self.end_headers()

    def _run_oauth_flow(self):
        self._CallbackHandler.auth_code = None
        server = http.server.HTTPServer(("localhost", self._REDIRECT_PORT), self._CallbackHandler)
        thread = threading.Thread(target=server.handle_request)
        thread.start()

        verifier, challenge = self._generate_pkce_pair()

        authorize_url = (
            "https://developer.api.autodesk.com/authentication/v2/authorize"
            f"?response_type=code&client_id={self.aps_client_id}"
            f"&redirect_uri={urllib.parse.quote(self._REDIRECT_URI)}"
            "&scope=data:read"
            f"&code_challenge={challenge}&code_challenge_method=S256"
        )
        webbrowser.open(authorize_url)
        thread.join(timeout=30)

        if not self._CallbackHandler.auth_code:
            raise RuntimeError("Autodesk login timed out or was cancelled.")

        resp = requests.post(
            f"{self.api_base}/oauth/exchange",
            json={
                "code": self._CallbackHandler.auth_code,
                "redirect_uri": self._REDIRECT_URI,
                "code_verifier": verifier,
            },
            timeout=15,
        )

        resp.raise_for_status()
        session_token = resp.json()["session_token"]
        self._save_session_token(session_token)
        return session_token

    # ---------------- internals: cert issuance ----------------

    def _issue_new_cert(self):
        session_token = self._load_session_token() or self._run_oauth_flow()

        resp = requests.post(
            f"{self.api_base}/cert/issue",
            headers={"Authorization": f"Bearer {session_token}"},
            timeout=15,
        )
        if resp.status_code == 401:
            # Session expired (idle 15+ days, or revoked) -> re-login, retry once.
            session_token = self._run_oauth_flow()
            resp = requests.post(
                f"{self.api_base}/cert/issue",
                headers={"Authorization": f"Bearer {session_token}"},
                timeout=15,
            )
        resp.raise_for_status()
        self._cert = resp.json()
        _save_cert(self)
        return self._cert

class EmailClient:
    api_base = "https://4a9iyrcgl5.execute-api.us-east-1.amazonaws.com".rstrip("/")
    _cert = None

    def __init__(self, cert_file=None):
        self._cert_file = cert_file or os.path.join(
            os.path.dirname(__file__), "cert.json"
        )
        self._cert = _load_cert(self)

    def get_address(self):
        resp = requests.get(
            f"{self.api_base}/email/get-address",
            headers={"X-Cert-Id": self._cert["cert_id"]},
            timeout=30,
        )
        if resp.status_code == 429:
            raise PermissionError("there is a maximum of 10 email operations a day")
        resp.raise_for_status()
        return resp.json()["email"]

    def get_activation_link(self, email):
        resp = requests.get(
            f"{self.api_base}/email/get-mail",
            headers={"X-Cert-Id": self._cert["cert_id"], "email": email},
            timeout=30,
        )
        if resp.status_code == 429:
            raise PermissionError("there is a maximum of 10 email operations a day")
        resp.raise_for_status()
        messages = resp.json()
        if not isinstance(messages, list):
            if messages.get("error") is not None:
                return False
            raise ValueError("Request returned unknown format")

        for message in messages:
            if message.get("mail_text") is not None:
                return self._extract_link(message.get("mail_text"))

        return False

    def _extract_link(self, message):
        charlist = []
        for char in message:
            charlist.append(char)

        target = "Confirm Account"
        i = 0
        for index, char in enumerate(charlist):
            i = index
            found = True
            for index2, correctChar in enumerate(target):
                if charlist[i] == correctChar:
                    i+=1
                else:
                    found = False
                    break
            if found:
                i+=2
                break
        link = ""

        while (charlist[i] != ']'):
            link+=charlist[i]
            i+=1

        return link

    