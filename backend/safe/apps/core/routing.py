"""Rotte WebSocket. Il consumer realtime viene implementato in M1 (auth) e M4/M5 (eventi)."""

from django.urls import URLPattern

websocket_urlpatterns: list[URLPattern] = []
