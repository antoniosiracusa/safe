"""Contesto tenant corrente (per richiesta o per job), basato su contextvars.

Tre livelli di isolamento (docs/01-architettura.md §3.2):
1. il middleware imposta il tenant dall'utente autenticato, mai da parametri client;
2. TenantManager filtra ogni queryset con il tenant corrente;
3. Row Level Security in PostgreSQL con `SET LOCAL app.company_id`.
"""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection, transaction

_current_company: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "safe_company", default=None
)
_bypass: contextvars.ContextVar[bool] = contextvars.ContextVar("safe_bypass_rls", default=False)


def get_current_company_id() -> uuid.UUID | None:
    return _current_company.get()


def is_bypass() -> bool:
    return _bypass.get()


def _set_local(company_id: uuid.UUID | None, bypass: bool) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.company_id', %s, true)", [str(company_id) if company_id else ""])
        cur.execute("SELECT set_config('app.bypass_rls', %s, true)", ["on" if bypass else "off"])


@contextmanager
def tenant_context(company_id: uuid.UUID) -> Iterator[None]:
    """Esegue il blocco in una transazione con il tenant impostato (usato da middleware e job)."""
    prev_company, prev_bypass = _current_company.get(), _bypass.get()
    token = _current_company.set(company_id)
    token_b = _bypass.set(False)
    try:
        with transaction.atomic():
            _set_local(company_id, False)
            try:
                yield
            finally:
                _set_local(prev_company, prev_bypass)
    finally:
        _bypass.reset(token_b)
        _current_company.reset(token)


@contextmanager
def bypass_tenant() -> Iterator[None]:
    """Solo per comandi di piattaforma (creazione società, retention globale, seed). Tracciato in audit."""
    prev_company, prev_bypass = _current_company.get(), _bypass.get()
    token = _bypass.set(True)
    try:
        with transaction.atomic():
            _set_local(None, True)
            try:
                yield
            finally:
                _set_local(prev_company, prev_bypass)
    finally:
        _bypass.reset(token)
