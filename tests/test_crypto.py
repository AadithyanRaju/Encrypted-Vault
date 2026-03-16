"""Tests for crypto/aead.py and crypto/hash.py."""
import os
import pytest

from cryptography.exceptions import InvalidTag

from crypto.aead import aead_encrypt, aead_decrypt
from crypto.hash import sha3_512_bytes, derive_kmaster


# ---------------------------------------------------------------------------
# AES-256-GCM (AEAD) tests
# ---------------------------------------------------------------------------

class TestAeadEncryptDecrypt:
    KEY = os.urandom(32)

    def test_encrypt_returns_nonce_and_ciphertext(self):
        nonce, ct = aead_encrypt(self.KEY, b"plaintext")
        assert len(nonce) == 12
        assert ct != b"plaintext"

    def test_ciphertext_differs_from_plaintext(self):
        nonce, ct = aead_encrypt(self.KEY, b"secret data")
        assert ct != b"secret data"

    def test_decrypt_recovers_plaintext(self):
        plaintext = b"round-trip test"
        nonce, ct = aead_encrypt(self.KEY, plaintext)
        recovered = aead_decrypt(self.KEY, nonce, ct)
        assert recovered == plaintext

    def test_decrypt_with_aad_roundtrip(self):
        plaintext = b"data with aad"
        aad = b"additional authenticated data"
        nonce, ct = aead_encrypt(self.KEY, plaintext, aad)
        recovered = aead_decrypt(self.KEY, nonce, ct, aad)
        assert recovered == plaintext

    def test_decrypt_wrong_key_raises(self):
        nonce, ct = aead_encrypt(self.KEY, b"sensitive")
        wrong_key = os.urandom(32)
        with pytest.raises(InvalidTag):
            aead_decrypt(wrong_key, nonce, ct)

    def test_decrypt_wrong_nonce_raises(self):
        nonce, ct = aead_encrypt(self.KEY, b"sensitive")
        bad_nonce = os.urandom(12)
        with pytest.raises(InvalidTag):
            aead_decrypt(self.KEY, bad_nonce, ct)

    def test_decrypt_tampered_ciphertext_raises(self):
        nonce, ct = aead_encrypt(self.KEY, b"tamper test")
        tampered = bytearray(ct)
        tampered[0] ^= 0xFF
        with pytest.raises(InvalidTag):
            aead_decrypt(self.KEY, nonce, bytes(tampered))

    def test_decrypt_wrong_aad_raises(self):
        plaintext = b"aad mismatch"
        aad = b"correct aad"
        nonce, ct = aead_encrypt(self.KEY, plaintext, aad)
        with pytest.raises(InvalidTag):
            aead_decrypt(self.KEY, nonce, ct, b"wrong aad")

    def test_nonces_are_unique(self):
        nonces = {aead_encrypt(self.KEY, b"x")[0] for _ in range(50)}
        assert len(nonces) == 50

    def test_empty_plaintext_roundtrip(self):
        nonce, ct = aead_encrypt(self.KEY, b"")
        recovered = aead_decrypt(self.KEY, nonce, ct)
        assert recovered == b""

    def test_large_plaintext_roundtrip(self):
        plaintext = os.urandom(1024 * 1024)  # 1 MiB
        nonce, ct = aead_encrypt(self.KEY, plaintext)
        recovered = aead_decrypt(self.KEY, nonce, ct)
        assert recovered == plaintext


# ---------------------------------------------------------------------------
# SHA-3-512 tests
# ---------------------------------------------------------------------------

class TestSha3512:
    def test_output_length(self):
        digest = sha3_512_bytes(b"hello")
        assert len(digest) == 64  # 512 bits

    def test_deterministic(self):
        assert sha3_512_bytes(b"abc") == sha3_512_bytes(b"abc")

    def test_different_inputs_different_digests(self):
        assert sha3_512_bytes(b"abc") != sha3_512_bytes(b"abd")

    def test_empty_input(self):
        digest = sha3_512_bytes(b"")
        assert len(digest) == 64


# ---------------------------------------------------------------------------
# Key-derivation (Argon2id) tests
# ---------------------------------------------------------------------------

class TestDeriveKmaster:
    SALT = os.urandom(16)

    def test_output_length(self):
        key = derive_kmaster("password", self.SALT, t_cost=1, m_cost_kib=8, parallelism=1)
        assert len(key) == 32

    def test_deterministic(self):
        k1 = derive_kmaster("pw", self.SALT, t_cost=1, m_cost_kib=8, parallelism=1)
        k2 = derive_kmaster("pw", self.SALT, t_cost=1, m_cost_kib=8, parallelism=1)
        assert k1 == k2

    def test_different_passphrases_different_keys(self):
        k1 = derive_kmaster("pw1", self.SALT, t_cost=1, m_cost_kib=8, parallelism=1)
        k2 = derive_kmaster("pw2", self.SALT, t_cost=1, m_cost_kib=8, parallelism=1)
        assert k1 != k2

    def test_different_salts_different_keys(self):
        salt2 = os.urandom(16)
        k1 = derive_kmaster("pw", self.SALT, t_cost=1, m_cost_kib=8, parallelism=1)
        k2 = derive_kmaster("pw", salt2, t_cost=1, m_cost_kib=8, parallelism=1)
        assert k1 != k2

    def test_unicode_passphrase(self):
        key = derive_kmaster("pässwörd-日本語", self.SALT, t_cost=1, m_cost_kib=8, parallelism=1)
        assert len(key) == 32
