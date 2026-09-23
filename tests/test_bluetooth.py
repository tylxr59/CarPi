"""Synthetic SDP service records, not copied from a vehicle."""

import unittest

from carpi.bluetooth import parse_sdp, select_channel


class SDPTests(unittest.TestCase):
    def test_select_named_iap_service(self):
        output = """Service RecHandle: 0x10001
Service Name: Handsfree
  Channel: 2
Service RecHandle: 0x10002
Service Name: Wireless iAP2
  Channel: 4
"""
        self.assertEqual(select_channel(parse_sdp(output)), 4)

    def test_select_uuid_service(self):
        output = """Service RecHandle: 0x10002
  UUID 128: 00000000-deca-fade-deca-deafdecacafe
  Channel: 3
"""
        self.assertEqual(select_channel(parse_sdp(output)), 3)

    def test_ambiguous_requires_override(self):
        with self.assertRaises(RuntimeError):
            select_channel([(2, "iAP"), (3, "iAP2")])


if __name__ == "__main__":
    unittest.main()
