"""Test runner that guarantees no test reaches a real, billed provider.

A developer `.env` holds live Azure OpenAI and ElevenLabs keys. Blanking them for the whole run means a code path
a test forgot to mock fails as "not configured" instead of making a live call. Tests that need a configured
provider still set their own values with override_settings and mock the client.
"""

from django.test.runner import DiscoverRunner
from django.test.utils import override_settings

PROVIDER_SETTINGS = {
    "AZURE_OPENAI_ENDPOINT": "",
    "AZURE_OPENAI_API_KEY": "",
    "AZURE_OPENAI_CHAT_DEPLOYMENT": "",
    "ELEVENLABS_API_KEY": "",
    "ELEVENLABS_AGENT_ID": "",
    "ELEVENLABS_WEBHOOK_SECRET": "",
    "TWILIO_ACCOUNT_SID": "",
    "TWILIO_AUTH_TOKEN": "",
}


class ProviderSafeTestRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._provider_override = override_settings(**PROVIDER_SETTINGS)
        self._provider_override.enable()

    def teardown_test_environment(self, **kwargs):
        self._provider_override.disable()
        super().teardown_test_environment(**kwargs)
