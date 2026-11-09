"""License checks: python -m unittest tests.test_license -v."""
import base64
import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from utils import license_utils as lic


def b64e(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_key(private_key, product, machine_id, expiry):
    """Same format as generate_license_key() in license_tool."""
    payload = f"{product}|{machine_id}|{expiry}".encode()
    return f"{b64e(payload)}.{b64e(private_key.sign(payload))}"


class LicenseKeyTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        public_hex = self.private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
        self.machine_id = lic.get_machine_id()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "license.dat")
        for name, value in (("PUBLIC_KEY_HEX", public_hex), ("LICENSE_FILE", self.path),
                            ("_LEGACY_LICENSE_FILES", [])):
            patcher = mock.patch.object(lic, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def key(self, product=lic.PRODUCT, machine_id=None, expiry="2099-12-31"):
        return make_key(self.private_key, product, machine_id or self.machine_id, expiry)

    def test_valid_key(self):
        self.assertTrue(lic.verify_license_key(self.key())[0])

    def test_key_survives_whitespace_from_chat_apps(self):
        key = self.key()
        self.assertTrue(lic.verify_license_key(f" {key[:20]}\n{key[20:]} ")[0])

    def test_key_expiring_today_is_still_valid(self):
        self.assertTrue(lic.verify_license_key(self.key(expiry=date.today().isoformat()))[0])

    def test_expired_key(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        ok, message = lic.verify_license_key(self.key(expiry=yesterday))
        self.assertFalse(ok)
        self.assertIn("hết hạn", message)

    def test_other_product_rejected(self):
        self.assertEqual(lic.verify_license_key(self.key(product="GIAPHA")),
                         (False, "License Key không hợp lệ"))

    def test_other_machine_rejected(self):
        ok, message = lic.verify_license_key(self.key(machine_id="0" * 32))
        self.assertFalse(ok)
        self.assertIn("Code", message)

    def test_key_signed_by_other_private_key_rejected(self):
        forged = make_key(Ed25519PrivateKey.generate(), lic.PRODUCT, self.machine_id, "2099-12-31")
        self.assertEqual(lic.verify_license_key(forged), (False, "License Key không hợp lệ"))

    def test_tampered_payload_rejected(self):
        sig = self.key().split(".")[1]
        payload = f"{lic.PRODUCT}|{self.machine_id}|2199-12-31".encode()
        self.assertEqual(lic.verify_license_key(f"{b64e(payload)}.{sig}"),
                         (False, "License Key không hợp lệ"))

    def test_old_hmac_key_rejected(self):
        payload = f"{self.machine_id}|2099-12-31"
        old_key = base64.b64encode(f"{payload}|{lic.sign(payload)}".encode()).decode()
        ok, message = lic.verify_license_key(old_key)
        self.assertFalse(ok)
        self.assertIn("phiên bản cũ", message)

    def test_garbage_rejected(self):
        for key in ("", "a.b.c", "!!!.???"):
            self.assertFalse(lic.verify_license_key(key)[0], key)

    def test_saved_license_round_trip(self):
        self.assertFalse(lic.check_license())
        self.assertIsNone(lic.get_license_info())
        self.assertTrue(lic.save_license(self.key(expiry="2099-12-31")))
        self.assertTrue(lic.check_license())
        info = lic.get_license_info()
        self.assertEqual(info["machine_id"], self.machine_id)
        self.assertEqual(info["expiry_date"], "2099-12-31")

    def test_saved_old_key_is_not_licensed(self):
        payload = f"{self.machine_id}|2099-12-31"
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(base64.b64encode(f"{payload}|{lic.sign(payload)}".encode()).decode())
        self.assertFalse(lic.check_license())
        self.assertIsNone(lic.get_license_info())


if __name__ == "__main__":
    unittest.main()
