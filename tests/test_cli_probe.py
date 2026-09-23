"""Probe reporting tests without Bluetooth hardware."""

import unittest
from types import SimpleNamespace

from carpi.cli import _probe_summary, parser
from carpi.probe import Authentication, State


def fake_probe(state=State.WIFI_RECEIVED, auth=Authentication.UNVERIFIED_ACCEPTED, wifi=True):
    return SimpleNamespace(state=state, authentication=auth, wifi_received=wifi)


class SummaryTests(unittest.TestCase):
    def test_flag_defaults_off_and_requires_explicit_probe_option(self):
        self.assertFalse(
            parser()
            .parse_args(["probe", "--target", "AA:BB:CC:DD:EE:FF"])
            .allow_unverified_accessory
        )
        self.assertTrue(
            parser()
            .parse_args(["probe", "--target", "AA:BB:CC:DD:EE:FF", "--allow-unverified-accessory"])
            .allow_unverified_accessory
        )

    def test_success_summary(self):
        text = _probe_summary(True, fake_probe(), None)
        self.assertIn("Bluetooth connection       OK", text)
        self.assertIn("UNVERIFIED - accepted by research flag", text)
        self.assertIn("Wi-Fi config received      YES", text)
        self.assertIn("CarPlay IP session         NOT ATTEMPTED", text)

    def test_failure_summary(self):
        text = _probe_summary(
            True,
            fake_probe(State.NEGOTIATING, Authentication.NOT_REACHED, False),
            "peer did not ACK",
        )
        self.assertIn("iAP2 link negotiation      FAILED", text)
        self.assertIn("SYN/SYN-ACK negotiation", text)
        self.assertIn("peer did not ACK", text)


if __name__ == "__main__":
    unittest.main()
