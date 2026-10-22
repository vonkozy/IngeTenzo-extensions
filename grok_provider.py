# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 — community extension for IngeTrazo.
#
# xAI Grok provider for the built-in AI Assistant.
#
# Adds "xAI (Grok)" next to Groq, Gemini, OpenRouter and the others.
# The assistant keeps its own chat, screenshots, Models list and Test
# connection button. Calls go straight to https://api.x.ai/v1 (OpenAI-
# compatible). The key is stored in your user profile, never in the .igz.
#
# Install
#   Extensions → Open plugins folder
#   Save this file as grok_provider.py and restart IngeTrazo.
#   Extensions → AI Assistant → Provider: xAI (Grok)
#   Paste a key from https://console.x.ai/ (starts with xai-)
#   Models → pick one → Test connection
#
# Version of this file is recorded below. Bump VERSION and add a CHANGELOG
# line when you change it, the same way as the camera-history extension.

VERSION = "0.01"
# Tested against IngeTrazo 0.5.9 (plugin API 2). The AI provider list lives
# in core.ai and is not a public extension hook, so this monkey-patches it
# the same way the built-in assistant reads it. If a future IngeTrazo adds
# xAI itself, this file becomes a no-op.
TESTED_INGETRAZO = "0.5.9"

# CHANGELOG
# 0.01 — 2026-10-22
#   Registers the xAI provider (base URL, default model, vision, key URL,
#   prefix detection for keys that start with xai-).
#   Injects the provider into the AI Assistant combo when the panel already
#   exists. Menu entry "Enable Grok (xAI)" does the same on demand.
#   Default model is grok-4.7 (xAI flagship as of October 2026). Use the
#   Models button if your key does not have that id.

from tools.base import Tool

_KEY_URL = "https://console.x.ai/"
_BASE = "https://api.x.ai/v1"
_LABEL = "xAI (Grok)"
_DEFAULT_MODEL = "grok-4.7"
_PROVIDER = "xai"


def _register() -> None:
    """Add xAI to the shared provider tables the AI Assistant already reads."""
    from core import ai

    if _PROVIDER not in ai.PROVIDERS:
        ai.PROVIDERS = tuple(ai.PROVIDERS) + (_PROVIDER,)
    ai._OPENAI_BASES[_PROVIDER] = _BASE
    ai.DEFAULT_MODELS[_PROVIDER] = _DEFAULT_MODEL
    ai.VISION.add(_PROVIDER)
    ai.PROVIDER_INFO[_PROVIDER] = (_LABEL, _KEY_URL)

    # Wrap once. The marker keeps a second import from stacking wrappers.
    orig = getattr(ai.detect_provider, "_xai_orig", None)
    if orig is None:
        orig = ai.detect_provider

        def detect_provider(api_key: str) -> str:
            if api_key and str(api_key).startswith("xai-"):
                return _PROVIDER
            return orig(api_key)

        detect_provider._xai_orig = orig
        ai.detect_provider = detect_provider


def _inject(app_or_window) -> bool:
    """Add the combo item if the AI Assistant panel is already built."""
    window = getattr(app_or_window, "window", app_or_window)
    panel = getattr(window, "_ai_assistant", None)
    combo = getattr(panel, "_provider", None)
    if combo is None:
        return False
    if combo.findData(_PROVIDER) < 0:
        combo.addItem(_LABEL, _PROVIDER)
    return True


_register()


def setup(app) -> None:
    _register()
    _inject(app)


class EnableGrokProvider(Tool):
    name = "Enable Grok (xAI)"
    description = (
        "Add xAI Grok to the AI Assistant provider list "
        f"(v{VERSION}, tested on IngeTrazo {TESTED_INGETRAZO})."
    )

    def on_activate(self, viewport):
        _register()
        window = viewport.window()
        ok = _inject(window)
        if ok:
            viewport.flash_status(
                f"Grok is on the list (v{VERSION}). "
                "AI Assistant → xAI (Grok), key from console.x.ai.",
                5000,
            )
        else:
            viewport.flash_status(
                f"Grok registered (v{VERSION}). Open AI Assistant; "
                "if it is not on the list, restart IngeTrazo.",
                6000,
            )
