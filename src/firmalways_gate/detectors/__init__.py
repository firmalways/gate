"""Personal-data detectors. Each module exposes ``ENTITY_TYPE`` and ``detect(text) -> list[Entity]``."""

from . import (
    bank_account,
    birth_date,
    credit_card,
    email,
    ip_address,
    license_plate,
    line_id,
    nationality,
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
    "birth_date",
    "credit_card",
    "email",
    "ip_address",
    "line_id",
    "nationality",
    "license_plate",
    "passport",
    "phone",
    "secret",
    "sensitive",
    "thai_address",
    "thai_id",
    "thai_name",
]
