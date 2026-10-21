from dataclasses import replace

import pytest

from app.config import AUTH_SECRET_DEFAULT, DEMO_NONCE_DEFAULT, Settings, validate_settings


def production(**overrides):
    base = replace(Settings(), app_env="production", demo_nonce_secret="x" * 32, auth_secret="y" * 32,
                   frontend_origin="https://trip.example", email_backend="smtp", smtp_host="smtp.example",
                   auth_dev_return_code=False, payment_provider="stripe", stripe_secret_key="sk_test_x",
                   stripe_webhook_secret="whsec_x", supplier_base_url="https://supplier.example",
                   redis_url="redis://redis:6379/0", sms_backend="off")
    return replace(base, **overrides)


def test_development_defaults_are_accepted():
    validate_settings(replace(Settings(), app_env="development", demo_nonce_secret=DEMO_NONCE_DEFAULT))


def test_production_accepts_explicit_secret_and_https_origin():
    validate_settings(production())


@pytest.mark.parametrize("secret", [DEMO_NONCE_DEFAULT, "short-secret"])
def test_production_rejects_demo_or_weak_nonce_secret(secret):
    with pytest.raises(RuntimeError, match="DEMO_NONCE_SECRET"):
        validate_settings(production(demo_nonce_secret=secret))


def test_production_rejects_plain_http_origin():
    with pytest.raises(RuntimeError, match="FRONTEND_ORIGIN"):
        validate_settings(production(frontend_origin="http://trip.example"))


@pytest.mark.parametrize("overrides", [{"app_env": "staging"}, {"model_mode": "live"},
                                       {"llm_provider": "other"}, {"case_create_limit_per_ip": 0}])
def test_invalid_settings_are_rejected(overrides):
    with pytest.raises(RuntimeError):
        validate_settings(replace(Settings(), **overrides))


@pytest.mark.parametrize("secret", [AUTH_SECRET_DEFAULT, "short"])
def test_production_rejects_demo_or_weak_auth_secret(secret):
    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        validate_settings(production(auth_secret=secret))


def test_production_requires_real_email_delivery_and_hidden_codes():
    with pytest.raises(RuntimeError, match="EMAIL_BACKEND"):
        validate_settings(production(email_backend="console"))
    with pytest.raises(RuntimeError, match="AUTH_DEV_RETURN_CODE"):
        validate_settings(production(auth_dev_return_code=True))


def test_smtp_backend_requires_a_host():
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        validate_settings(replace(Settings(), email_backend="smtp", smtp_host=""))


def test_production_requires_stripe_and_a_real_supplier():
    with pytest.raises(RuntimeError, match="PAYMENT_PROVIDER"):
        validate_settings(production(payment_provider="simulated"))
    with pytest.raises(RuntimeError, match="STRIPE_WEBHOOK_SECRET"):
        validate_settings(production(stripe_webhook_secret=""))
    with pytest.raises(RuntimeError, match="SUPPLIER_BASE_URL"):
        validate_settings(production(supplier_base_url=""))


def test_stripe_provider_needs_a_secret_key():
    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY"):
        validate_settings(replace(Settings(), payment_provider="stripe", stripe_secret_key="pk_test_wrong"))


def test_production_requires_a_shared_rate_limit_store():
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        validate_settings(production(redis_url=""))


def test_text_messages_need_a_real_provider_in_production():
    with pytest.raises(RuntimeError, match="SMS_BACKEND"):
        validate_settings(production(sms_backend="console"))
    with pytest.raises(RuntimeError, match="TWILIO"):
        validate_settings(production(sms_backend="twilio"))
    validate_settings(production(sms_backend="twilio", twilio_account_sid="AC1", twilio_auth_token="t", twilio_from="+6400"))
