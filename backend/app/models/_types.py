from enum import Enum
from typing import Type

from sqlalchemy import Enum as SAEnum


def enum_col(enum_cls: Type[Enum]) -> SAEnum:
    """Store a Python Enum as plain text (VARCHAR) instead of a Postgres ENUM type.

    Adding a new value later then needs no database migration of the type.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
