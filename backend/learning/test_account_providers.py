from django.test import SimpleTestCase, override_settings

from .account_providers import CAPABILITY_NAMES, provider_configuration_state


class ProviderCapabilityTests(SimpleTestCase):
    @override_settings(LEARNING_ACCOUNT_PROVIDER_BACKEND="")
    def test_missing_provider_disables_all_dependent_capabilities(self):
        state = provider_configuration_state()
        self.assertFalse(state["provider_configured"])
        self.assertFalse(state["provider_ready"])
        self.assertEqual(state["status"], "provider_not_configured")
        self.assertEqual(set(state["capabilities"]), set(CAPABILITY_NAMES))
        self.assertFalse(any(state["capabilities"].values()))

    @override_settings(LEARNING_ACCOUNT_PROVIDER_BACKEND="example.Provider")
    def test_setting_a_path_does_not_falsely_mark_an_incomplete_adapter_ready(self):
        state = provider_configuration_state()
        self.assertTrue(state["provider_configured"])
        self.assertFalse(state["provider_ready"])
        self.assertEqual(state["status"], "provider_adapter_integration_incomplete")
        self.assertFalse(any(state["capabilities"].values()))
