"""Personal-data detectors. Each module exposes ``ENTITY_TYPE`` and ``detect(text) -> list[Entity]``."""

from . import (
    bank_account,
    credit_card,
    email,
    ip_address,
    line_id,
    license_plate,
    passport,
    phone,
    secret,
    sensitive,
    thai_address,
    thai_id,
    thai_name,
)

__all__ = [
    "bank_account",
    "credit_card",
    "email",
    "ip_address",
    "line_id",
    "license_plate",
    "passport",
    "phone",
    "secret",
    "sensitive",
    "thai_address",
    "thai_id",
    "thai_name",
]
