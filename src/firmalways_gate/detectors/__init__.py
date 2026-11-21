"""Personal-data detectors. Each module exposes ``ENTITY_TYPE`` and ``detect(text) -> list[Entity]``."""

from . import bank_account, credit_card, email, phone, secret, thai_address, thai_id, thai_name

__all__ = ["bank_account", "credit_card", "email", "phone", "secret", "thai_address", "thai_id", "thai_name"]
