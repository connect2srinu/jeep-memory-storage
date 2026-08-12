"""Preference domain and infrastructure adapters."""

from .models import EffectivePreferenceContext, Preference, PreferenceCandidate, PreferenceSource
from .resolver import PreferenceResolver

__all__ = [
    "EffectivePreferenceContext",
    "Preference",
    "PreferenceCandidate",
    "PreferenceResolver",
    "PreferenceSource",
]
