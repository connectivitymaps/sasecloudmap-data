import pytest


def test_http_request_kwargs_uses_default_trust_store_when_no_extra_ca(monkeypatch):
    from provider_data.utils import http as http_utils

    monkeypatch.delenv("EXTRA_CA_CERT_FILE", raising=False)
    monkeypatch.setattr(http_utils, "load_dotenv", lambda: None)
    http_utils.http_request_kwargs.cache_clear()

    assert http_utils.http_request_kwargs() == {}


def test_http_request_kwargs_builds_ssl_context_from_extra_ca(monkeypatch, tmp_path):
    from provider_data.utils import http as http_utils

    extra_bundle = tmp_path / "extra.pem"
    extra_bundle.write_text("EXTRA-CA\n", encoding="utf-8")

    class FakeSSLContext:
        def __init__(self):
            self.verify_flags = 123
            self.loaded = []

        def load_verify_locations(self, *, cafile):
            self.loaded.append(cafile)

    fake_context = FakeSSLContext()

    monkeypatch.setenv("EXTRA_CA_CERT_FILE", str(extra_bundle))
    monkeypatch.setattr(http_utils, "load_dotenv", lambda: None)
    monkeypatch.setattr(http_utils.ssl, "VERIFY_X509_STRICT", 32)
    monkeypatch.setattr(
        http_utils.ssl, "create_default_context", lambda cafile: fake_context
    )
    monkeypatch.setattr(http_utils.certifi, "where", lambda: "/tmp/certifi.pem")
    http_utils.http_request_kwargs.cache_clear()

    kwargs = http_utils.http_request_kwargs()

    assert set(kwargs) == {"verify"}
    assert kwargs["verify"] is fake_context
    assert fake_context.loaded == [str(extra_bundle)]
    assert fake_context.verify_flags == 123


def test_http_request_kwargs_can_explicitly_relax_x509_strict(monkeypatch, tmp_path):
    from provider_data.utils import http as http_utils

    extra_bundle = tmp_path / "extra.pem"
    extra_bundle.write_text("EXTRA-CA\n", encoding="utf-8")

    class FakeSSLContext:
        def __init__(self):
            self.verify_flags = 123
            self.loaded = []

        def load_verify_locations(self, *, cafile):
            self.loaded.append(cafile)

    fake_context = FakeSSLContext()

    monkeypatch.setenv("EXTRA_CA_CERT_FILE", str(extra_bundle))
    monkeypatch.setenv("RELAX_X509_STRICT", "1")
    monkeypatch.setattr(http_utils, "load_dotenv", lambda: None)
    monkeypatch.setattr(http_utils.ssl, "VERIFY_X509_STRICT", 32)
    monkeypatch.setattr(
        http_utils.ssl, "create_default_context", lambda cafile: fake_context
    )
    monkeypatch.setattr(http_utils.certifi, "where", lambda: "/tmp/certifi.pem")
    http_utils.http_request_kwargs.cache_clear()

    kwargs = http_utils.http_request_kwargs()

    assert kwargs["verify"] is fake_context
    assert fake_context.verify_flags == 123 & ~32


def test_http_request_kwargs_fails_fast_for_missing_extra_ca(monkeypatch):
    from provider_data.utils import http as http_utils

    monkeypatch.setenv("EXTRA_CA_CERT_FILE", "/missing/corp-ca.pem")
    monkeypatch.setattr(http_utils, "load_dotenv", lambda: None)
    http_utils.http_request_kwargs.cache_clear()

    with pytest.raises(FileNotFoundError, match="EXTRA_CA_CERT_FILE"):
        http_utils.http_request_kwargs()
