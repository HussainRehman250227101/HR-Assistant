"""ElevenLabs Conversational AI outbound calling over its native Twilio integration.

ElevenLabs places the call through the Twilio number imported into ElevenLabs
(`ELEVENLABS_AGENT_PHONE_NUMBER_ID`). Twilio's REST API is queried directly for
the authoritative telephony status (no-answer / busy / failed / completed).
Credentials are read from settings only and never logged or returned to clients.
"""

import hashlib
import hmac
import logging
import time

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

PROVIDER_NAME = "elevenlabs_twilio"


class VoiceConfigurationError(Exception):
    pass


class VoiceProviderError(Exception):
    pass


def configuration_status():
    """Booleans only - safe to expose to administrators."""
    return {
        "telephony_provider": settings.TELEPHONY_PROVIDER,
        "voice_ai_provider": settings.VOICE_AI_PROVIDER,
        "elevenlabs_api_key": bool(settings.ELEVENLABS_API_KEY),
        "elevenlabs_agent_id": bool(settings.ELEVENLABS_AGENT_ID),
        "elevenlabs_agent_phone_number_id": bool(settings.ELEVENLABS_AGENT_PHONE_NUMBER_ID),
        "elevenlabs_webhook_secret": bool(settings.ELEVENLABS_WEBHOOK_SECRET),
        "twilio_account_sid": bool(settings.TWILIO_ACCOUNT_SID),
        "twilio_auth_token": bool(settings.TWILIO_AUTH_TOKEN),
        "twilio_phone_number": bool(settings.TWILIO_PHONE_NUMBER),
        "allowed_dial_prefixes": list(settings.SCREENING_ALLOWED_DIAL_PREFIXES),
    }


class ElevenLabsTwilioVoiceClient:
    def __init__(self, http_client=None):
        self._http = http_client

    @property
    def is_configured(self):
        return (
            settings.TELEPHONY_PROVIDER == "twilio"
            and settings.VOICE_AI_PROVIDER == "elevenlabs"
            and all((
                settings.ELEVENLABS_API_KEY,
                settings.ELEVENLABS_AGENT_ID,
                settings.ELEVENLABS_AGENT_PHONE_NUMBER_ID,
            ))
        )

    @property
    def http(self):
        if self._http is None:
            self._http = httpx.Client(timeout=settings.VOICE_PROVIDER_TIMEOUT_SECONDS)
        return self._http

    def _el_headers(self):
        return {"xi-api-key": settings.ELEVENLABS_API_KEY, "Content-Type": "application/json"}

    def _el_url(self, path):
        return f"{settings.ELEVENLABS_API_BASE_URL.rstrip('/')}{path}"

    def _request(self, method, url, operation, **kwargs):
        try:
            response = self.http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            logger.warning("Voice provider request failed. operation=%s exception_type=%s", operation, type(exc).__name__)
            raise VoiceProviderError(f"The voice provider could not be reached ({operation}).") from exc
        if response.status_code >= 400:
            logger.warning("Voice provider returned an error. operation=%s status=%s", operation, response.status_code)
            raise VoiceProviderError(f"The voice provider rejected the request ({operation}, HTTP {response.status_code}).")
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise VoiceProviderError(f"The voice provider returned an invalid response ({operation}).") from exc

    def start_outbound_call(self, to_number, dynamic_variables):
        if not self.is_configured:
            raise VoiceConfigurationError(
                "Twilio/ElevenLabs calling is not configured. Set ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID and "
                "ELEVENLABS_AGENT_PHONE_NUMBER_ID (the Twilio number imported into ElevenLabs)."
            )
        payload = {
            "agent_id": settings.ELEVENLABS_AGENT_ID,
            "agent_phone_number_id": settings.ELEVENLABS_AGENT_PHONE_NUMBER_ID,
            "to_number": to_number,
            "conversation_initiation_client_data": {"dynamic_variables": dynamic_variables},
        }
        data = self._request(
            "POST", self._el_url("/v1/convai/twilio/outbound-call"), "outbound_call",
            headers=self._el_headers(), json=payload,
        )
        if data.get("success") is False:
            raise VoiceProviderError("ElevenLabs did not accept the outbound call request.")
        conversation_id = data.get("conversation_id")
        call_sid = data.get("callSid") or data.get("call_sid") or ""
        if not conversation_id and not call_sid:
            raise VoiceProviderError("ElevenLabs did not return a conversation or call identifier.")
        return {"conversation_id": conversation_id, "call_sid": call_sid}

    def get_conversation(self, conversation_id):
        if not settings.ELEVENLABS_API_KEY:
            raise VoiceConfigurationError("ELEVENLABS_API_KEY is not configured.")
        return self._request(
            "GET", self._el_url(f"/v1/convai/conversations/{conversation_id}"), "get_conversation",
            headers=self._el_headers(),
        )

    def delete_conversation(self, conversation_id):
        if not settings.ELEVENLABS_API_KEY:
            raise VoiceConfigurationError("ELEVENLABS_API_KEY is not configured.")
        self._request(
            "DELETE", self._el_url(f"/v1/convai/conversations/{conversation_id}"), "delete_conversation",
            headers=self._el_headers(),
        )

    def get_twilio_call(self, call_sid):
        if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN):
            return None
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Calls/{call_sid}.json"
        return self._request(
            "GET", url, "twilio_call_status",
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
        )


def get_voice_client():
    return ElevenLabsTwilioVoiceClient()


def verify_elevenlabs_signature(raw_body: bytes, header: str, secret: str, tolerance_seconds=1800, now=None):
    """Validate the `ElevenLabs-Signature: t=<ts>,v0=<hex hmac>` header of post-call webhooks."""
    if not secret or not header:
        return False
    parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
    timestamp, signature = parts.get("t"), parts.get("v0")
    if not timestamp or not signature or not timestamp.isdigit():
        return False
    current = int(now if now is not None else time.time())
    if abs(current - int(timestamp)) > tolerance_seconds:
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
