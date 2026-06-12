"""Авторизация на основе cookie-сессии. Две роли: admin и user.

Учётные записи задаются переменными окружения (логин/пароль на роль).
Сессия хранится в подписанной cookie (Starlette SessionMiddleware).
"""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from app.config import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    ROLE_ADMIN,
    ROLE_USER,
    USER_PASSWORD,
    USER_USERNAME,
)

# username -> (password, role)
_ACCOUNTS: dict[str, tuple[str, str]] = {
    ADMIN_USERNAME: (ADMIN_PASSWORD, ROLE_ADMIN),
    USER_USERNAME: (USER_PASSWORD, ROLE_USER),
}


def authenticate(username: str, password: str) -> Optional[dict[str, str]]:
    """Проверить логин/пароль. Возвращает {'username', 'role'} или None."""
    account = _ACCOUNTS.get(username)
    if account is None:
        return None
    expected_password, role = account
    # Сравнение в постоянном времени.
    if not hmac.compare_digest(password, expected_password):
        return None
    return {"username": username, "role": role}


# --- Зависимости FastAPI -----------------------------------------------------
def current_user(request: Request) -> Optional[dict[str, str]]:
    """Текущий пользователь из сессии или None."""
    return request.session.get("user")


def require_login(request: Request) -> dict[str, str]:
    """Требовать авторизацию (любая роль). 401, если не вошёл."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация"
        )
    return user


def require_admin(user: dict[str, str] = Depends(require_login)) -> dict[str, str]:
    """Требовать роль admin. 403, если роль недостаточна."""
    if user.get("role") != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ только для администратора",
        )
    return user
