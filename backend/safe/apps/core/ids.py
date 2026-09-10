"""UUID v7 (ordinabili nel tempo) come chiave primaria di tutte le entità."""

import uuid

import uuid_utils


def uuid7() -> uuid.UUID:
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)
