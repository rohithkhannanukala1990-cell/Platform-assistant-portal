"""Slack connector — channels read + channel notify (webhook or bot token)."""

from __future__ import annotations

from typing import Any

import httpx

from .registry import SlackConnector as _BaseSlack


class SlackConnector(_BaseSlack):
    def _bot_token(self) -> str:
        return (
            self.account.get("api_key")
            or self.account.get("token")
            or self.account.get("bot_token")
            or self.account.get("credentials_vault_ref")
            or ""
        ).strip()

    def _webhook_url(self) -> str:
        return (
            self.account.get("webhook_url")
            or self.account.get("instance_url")
            or self.account.get("incoming_webhook")
            or ""
        ).strip()

    @property
    def configured(self) -> bool:
        return bool(self._bot_token() or self._webhook_url())

    async def ping(self) -> dict[str, Any]:
        token = self._bot_token()
        webhook = self._webhook_url()
        if not token and not webhook:
            return {
                "ok": False,
                "error": {"type": "not_configured", "message": "Slack bot token or webhook URL missing"},
            }
        if webhook and not token:
            return {"ok": True, "mode": "webhook", "message": "Incoming webhook configured"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                if resp.status_code == 401 or (isinstance(data, dict) and data.get("ok") is False and data.get("error") == "invalid_auth"):
                    return {"ok": False, "error": {"type": "auth_failed", "message": "invalid Slack token"}}
                if isinstance(data, dict) and data.get("ok"):
                    return {
                        "ok": True,
                        "mode": "bot",
                        "team": data.get("team"),
                        "user": data.get("user"),
                    }
                return {"ok": False, "error": {"type": "network_error", "message": str(data.get("error") or resp.text)[:200]}}
        except Exception as exc:
            return {"ok": False, "error": {"type": "network_error", "message": str(exc)[:200]}}

    async def list_channels(self, limit: int = 50) -> list[dict[str, Any]]:
        token = self._bot_token()
        if not token:
            # Webhook-only accounts cannot list channels.
            return []
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    "https://slack.com/api/conversations.list",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"limit": min(limit, 200), "types": "public_channel,private_channel"},
                )
                data = resp.json()
                if not isinstance(data, dict) or not data.get("ok"):
                    return []
                out = []
                for ch in data.get("channels") or []:
                    out.append(
                        {
                            "id": ch.get("id"),
                            "name": ch.get("name"),
                            "is_private": bool(ch.get("is_private")),
                            "num_members": ch.get("num_members"),
                        }
                    )
                return out[:limit]
        except Exception:
            return []

    async def notify_channel(
        self,
        *,
        text: str,
        channel: str | None = None,
    ) -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty message"}

        webhook = self._webhook_url()
        if webhook:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(webhook, json={"text": text})
                    if resp.status_code < 300:
                        return {"ok": True, "mode": "webhook", "status_code": resp.status_code}
                    return {"ok": False, "error": f"webhook HTTP {resp.status_code}", "body": resp.text[:200]}
            except Exception as exc:
                return {"ok": False, "error": str(exc)[:200]}

        token = self._bot_token()
        if not token:
            return {"ok": False, "error": "no Slack credentials"}
        channel = (channel or "").strip() or "#general"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"channel": channel, "text": text},
                )
                data = resp.json()
                ok = bool(isinstance(data, dict) and data.get("ok"))
                return {
                    "ok": ok,
                    "mode": "bot",
                    "channel": channel,
                    "error": None if ok else (data.get("error") if isinstance(data, dict) else "post failed"),
                }
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    async def post_thread_reply(
        self,
        channel: str,
        thread_ts: str,
        text: str,
        blocks: list | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        from .idempotency import ConnectorNotConfigured, recall_idempotent, store_idempotent

        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        token = self._bot_token()
        if not token:
            raise ConnectorNotConfigured("Slack")
        payload: dict[str, Any] = {
            "channel": channel,
            "thread_ts": thread_ts,
            "text": text or "",
        }
        if blocks:
            payload["blocks"] = blocks
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if not isinstance(data, dict) or not data.get("ok"):
            return {
                "ok": False,
                "error": (data.get("error") if isinstance(data, dict) else "post failed"),
            }
        ts = data.get("ts")
        out = {
            "ok": True,
            "channel": data.get("channel") or channel,
            "ts": ts,
            "thread_ts": thread_ts,
            "url": f"https://slack.com/archives/{channel}/p{str(ts or '').replace('.', '')}",
            "reused": False,
        }
        store_idempotent(idempotency_key, out)
        return out

    async def post_approval_request(
        self,
        channel: str,
        approval_id: str,
        summary: str,
        risk: str,
        detail_url: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        from .idempotency import ConnectorNotConfigured, recall_idempotent, store_idempotent
        from ..services.ssrf import assert_safe_outbound_url

        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        if not self._bot_token():
            raise ConnectorNotConfigured("Slack")
        if detail_url:
            assert_safe_outbound_url(detail_url)
        risk_label = (risk or "medium").upper()
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Approval required"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Summary*\n{summary or '(none)'}\n\n*Risk:* `{risk_label}`",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": "approve_request",
                        "value": str(approval_id),
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "action_id": "reject_request",
                        "value": str(approval_id),
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open in portal"},
                        "url": detail_url or "https://example.invalid",
                        "action_id": "open_detail",
                    },
                ],
            },
        ]
        token = self._bot_token()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "channel": channel,
                    "text": f"Approval request: {summary}",
                    "blocks": blocks,
                },
            )
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if not isinstance(data, dict) or not data.get("ok"):
            return {
                "ok": False,
                "error": (data.get("error") if isinstance(data, dict) else "post failed"),
            }
        ts = data.get("ts")
        out = {
            "ok": True,
            "channel": data.get("channel") or channel,
            "ts": ts,
            "approval_id": approval_id,
            "url": f"https://slack.com/archives/{channel}/p{str(ts or '').replace('.', '')}",
            "reused": False,
        }
        store_idempotent(idempotency_key, out)
        return out

    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: list | None = None,
    ) -> dict[str, Any]:
        from .idempotency import ConnectorNotConfigured

        token = self._bot_token()
        if not token:
            raise ConnectorNotConfigured("Slack")
        payload: dict[str, Any] = {"channel": channel, "ts": ts, "text": text or ""}
        if blocks:
            payload["blocks"] = blocks
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://slack.com/api/chat.update",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if not isinstance(data, dict) or not data.get("ok"):
            return {
                "ok": False,
                "error": (data.get("error") if isinstance(data, dict) else "update failed"),
            }
        return {
            "ok": True,
            "channel": channel,
            "ts": ts,
            "url": f"https://slack.com/archives/{channel}/p{str(ts or '').replace('.', '')}",
        }

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            if action == "ping":
                result = await self.ping()
                return {"ok": bool(result.get("ok")), "tool": "slack", "action": action, "result": result}
            if action == "list_channels":
                result = await self.list_channels(limit=int(params.get("limit", 50)))
                return {"ok": True, "tool": "slack", "action": action, "result": result}
            if action in ("notify", "notify_channel", "post_message"):
                result = await self.notify_channel(
                    text=str(params.get("text") or params.get("message") or ""),
                    channel=params.get("channel"),
                )
                return {"ok": bool(result.get("ok")), "tool": "slack", "action": action, "result": result}
            if action == "post_thread_reply":
                result = await self.post_thread_reply(
                    params.get("channel", ""),
                    params.get("thread_ts", ""),
                    params.get("text", ""),
                    blocks=params.get("blocks"),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "slack", "action": action, "result": result}
            if action == "post_approval_request":
                result = await self.post_approval_request(
                    params.get("channel", ""),
                    params.get("approval_id", ""),
                    params.get("summary", ""),
                    params.get("risk", "medium"),
                    params.get("detail_url", ""),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "slack", "action": action, "result": result}
            if action == "update_message":
                result = await self.update_message(
                    params.get("channel", ""),
                    params.get("ts", ""),
                    params.get("text", ""),
                    blocks=params.get("blocks"),
                )
                return {"ok": bool(result.get("ok")), "tool": "slack", "action": action, "result": result}
        except Exception as exc:
            return {"ok": False, "tool": "slack", "action": action, "error": str(exc)}
        return await super().execute_action(action, params)
