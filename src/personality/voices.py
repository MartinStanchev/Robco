"""Catalog of all 30 Gemini Live API HD voices.

Each voice has a name, description, and suggested personality fit.
Voice names are passed to Gemini's voiceConfig in the WebSocket setup.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceInfo:
    """Information about a Gemini voice.

    Attributes:
        name: Voice identifier used in Gemini API (e.g., "Achird").
        description: Short description of the voice character.
        personality_fit: Suggested use case for this voice.
    """

    name: str
    description: str
    personality_fit: str


VOICE_CATALOG: dict[str, VoiceInfo] = {
    "Achird": VoiceInfo("Achird", "Friendly", "Default warm assistant"),
    "Sulafat": VoiceInfo("Sulafat", "Warm", "Caring, empathetic"),
    "Puck": VoiceInfo("Puck", "Upbeat", "Energetic, fun"),
    "Zephyr": VoiceInfo("Zephyr", "Bright", "Cheerful, positive"),
    "Kore": VoiceInfo("Kore", "Firm", "Professional, authoritative"),
    "Charon": VoiceInfo("Charon", "Informative", "Educational, factual"),
    "Fenrir": VoiceInfo("Fenrir", "Excitable", "Enthusiastic, animated"),
    "Leda": VoiceInfo("Leda", "Youthful", "Young, casual"),
    "Aoede": VoiceInfo("Aoede", "Breezy", "Relaxed, easy-going"),
    "Gacrux": VoiceInfo("Gacrux", "Mature", "Serious, experienced"),
    "Sadaltager": VoiceInfo("Sadaltager", "Knowledgeable", "Expert, teacher-like"),
    "Vindemiatrix": VoiceInfo("Vindemiatrix", "Gentle", "Soft, calming"),
    "Sadachbia": VoiceInfo("Sadachbia", "Lively", "Spirited, engaging"),
    "Zubenelgenubi": VoiceInfo("Zubenelgenubi", "Casual", "Laid-back, informal"),
    "Pulcherrima": VoiceInfo("Pulcherrima", "Forward", "Direct, confident"),
    "Solaria": VoiceInfo("Solaria", "Crisp", "Clear, articulate"),
    "Umbriel": VoiceInfo("Umbriel", "Easy-going", "Relaxed, approachable"),
    "Algieba": VoiceInfo("Algieba", "Smooth", "Polished, refined"),
    "Despina": VoiceInfo("Despina", "Smooth", "Polished, pleasant"),
    "Erinome": VoiceInfo("Erinome", "Clear", "Precise, well-spoken"),
    "Algenib": VoiceInfo("Algenib", "Gravelly", "Rugged, distinctive"),
    "Rasalgethi": VoiceInfo("Rasalgethi", "Informative", "Thoughtful, measured"),
    "Laomedeia": VoiceInfo("Laomedeia", "Upbeat", "Positive, cheerful"),
    "Achernar": VoiceInfo("Achernar", "Soft", "Gentle, soothing"),
    "Enceladus": VoiceInfo("Enceladus", "Breathy", "Intimate, quiet"),
    "Iapetus": VoiceInfo("Iapetus", "Clear", "Bright, transparent"),
    "Callirrhoe": VoiceInfo("Callirrhoe", "Easy-going", "Calm, comfortable"),
    "Autonoe": VoiceInfo("Autonoe", "Bright", "Vivid, engaging"),
    "Orus": VoiceInfo("Orus", "Firm", "Strong, decisive"),
    "Schedar": VoiceInfo("Schedar", "Even", "Balanced, steady"),
}


def get_voice(name: str) -> VoiceInfo:
    """Get voice info by name (case-insensitive).

    Args:
        name: Voice name (e.g., "Achird", "achird").

    Returns:
        VoiceInfo for the requested voice.

    Raises:
        KeyError: If the voice name is not found in the catalog.
    """
    # Try exact match first, then case-insensitive
    if name in VOICE_CATALOG:
        return VOICE_CATALOG[name]

    name_lower = name.lower()
    for key, voice in VOICE_CATALOG.items():
        if key.lower() == name_lower:
            return voice

    raise KeyError(
        f"Voice '{name}' not found. Available voices: {', '.join(VOICE_CATALOG.keys())}"
    )


def list_voices() -> list[VoiceInfo]:
    """Return all available voices.

    Returns:
        List of all VoiceInfo objects in the catalog.
    """
    return list(VOICE_CATALOG.values())
