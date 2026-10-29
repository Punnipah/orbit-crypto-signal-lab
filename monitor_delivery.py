"""Telegram delivery + persisted alert outbox on a separate GitHub branch.

No GitHub/Telegram credentials are hardcoded. A dedicated branch avoids
Streamlit redeploys whenever only alert states change. GitHub Actions needs
`permissions: contents: write`; organization/branch restrictions may block it.
"""

from __future__ import annotations

import base64
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from monitor_alerts import empty_state, serialize_state, validate_state


STATE_BRANCH = "orbit-alert-state"
STATE_PATH = ".orbit-monitor/alert-state.json"


class DeliveryError(RuntimeError):
    pass


def send_telegram(token: str, chat_id: str, text: str) -> None:
    """Use official Bot API; never log the token or echo the response URL."""
    if not re.fullmatch(r"\d{5,15}:[A-Za-z0-9_-]{20,}", token):
        raise DeliveryError("TELEGRAM_BOT_TOKEN ยังไม่ตั้งค่าหรือรูปแบบผิด")
    if not re.fullmatch(r"-?\d{5,25}", chat_id):
        raise DeliveryError("TELEGRAM_CHAT_ID ต้องเป็นตัวเลขของผู้รับ")
    if not text or len(text) > 4000:
        raise DeliveryError("ข้อความ Telegram ต้องยาวไม่เกิน 4000 อักขระ")
    data = json.dumps({"chat_id": chat_id, "text": text,
                       "link_preview_options": {"is_disabled": True}}, ensure_ascii=False).encode("utf-8")
    req = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data,
                  headers={"Content-Type": "application/json", "User-Agent": "OrbitMonitor/4.1"},
                  method="POST")
    try:
        with urlopen(req, timeout=20) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        status = getattr(exc, "code", None)
        raise DeliveryError(f"ส่ง Telegram ไม่สำเร็จ (HTTP {status or 'network error'}); "
                            "ตรวจ Bot Token/Chat ID/การกด Start") from None
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise DeliveryError("Telegram ตอบกลับว่าไม่สำเร็จ; ตรวจ Bot Token/Chat ID")


class GitHubStateStore:
    """Small GitHub REST Contents store with an independent state branch."""

    def __init__(self, repository: str, token: str, default_sha: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise DeliveryError("GITHUB_REPOSITORY ไม่ถูกต้อง")
        if not token or not re.fullmatch(r"[0-9a-fA-F]{40}", default_sha):
            raise DeliveryError("GITHUB_TOKEN หรือ GITHUB_SHA ไม่พร้อม")
        self.root = f"https://api.github.com/repos/{repository}"
        self.token = token
        self.default_sha = default_sha
        self.exists = False
        self.file_sha: str | None = None
        self.current_blob: bytes | None = None

    def _request(self, method: str, path: str, body: dict | None = None, *,
                 missing_ok: bool = False) -> dict | None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
        req = Request(self.root + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "OrbitMonitor/4.1",
        })
        try:
            with urlopen(req, timeout=25) as response:
                value = json.load(response)
        except HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            raise DeliveryError(f"GitHub State API HTTP {exc.code}; "
                                "ตรวจสิทธิ์ contents:write และ Actions settings") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise DeliveryError("GitHub State API ติดต่อไม่ได้") from None
        if not isinstance(value, dict):
            raise DeliveryError("GitHub State API ตอบข้อมูลผิดรูปแบบ")
        return value

    def load(self) -> dict:
        ref_path = "/git/ref/heads/" + STATE_BRANCH
        self.exists = self._request("GET", ref_path, missing_ok=True) is not None
        if not self.exists:
            self.file_sha = None
            self.current_blob = None
            return empty_state()
        file_path = "/contents/" + quote(STATE_PATH, safe="/") + "?ref=" + STATE_BRANCH
        data = self._request("GET", file_path, missing_ok=True)
        if data is None:
            self.file_sha = None
            self.current_blob = None
            return empty_state()
        if data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
            raise DeliveryError("GitHub State ไม่ใช่ไฟล์ Base64")
        try:
            content = base64.b64decode(data["content"], validate=False)
            state = json.loads(content)
            validate_state(state)
        except (ValueError, TypeError, UnicodeError):
            raise DeliveryError("GitHub State เก่า/เสียหาย: หยุดส่งเพื่อป้องกันข้อความซ้ำ") from None
        self.file_sha = data.get("sha")
        self.current_blob = content
        return state

    def save(self, state: dict) -> bool:
        blob = serialize_state(state)
        if blob == self.current_blob:
            return False
        if not self.exists:
            self._request("POST", "/git/refs", {
                "ref": "refs/heads/" + STATE_BRANCH, "sha": self.default_sha,
            })
            self.exists = True
        body = {
            "message": "chore(orbit): persist Telegram monitor alerts [skip ci]",
            "content": base64.b64encode(blob).decode("ascii"),
            "branch": STATE_BRANCH,
        }
        if self.file_sha:
            body["sha"] = self.file_sha
        response = self._request("PUT", "/contents/" + quote(STATE_PATH, safe="/"), body)
        if not isinstance(response.get("content"), dict) or not response["content"].get("sha"):
            raise DeliveryError("GitHub State ไม่ยืนยัน SHA ของไฟล์ที่บันทึก")
        self.file_sha = response["content"]["sha"]
        self.current_blob = blob
        return True
