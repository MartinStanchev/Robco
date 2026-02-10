# Robco Voice Robot — Technical Design Document

**Version:** 3.0
**Last Updated:** February 8, 2026
**Status:** Design Phase — Gemini Live API Architecture

---

## 1. Executive Summary

Robco is a voice-interactive household robot powered by Google Gemini's Live API for native audio-to-audio conversation. The robot detects a wake word, opens a WebSocket session to Gemini, and engages in natural multi-turn conversation with bidirectional audio streaming. Gemini handles speech understanding, reasoning, and speech generation natively — no separate STT or TTS services required.

The architecture is extensible via MCP (Model Context Protocol) tools, enabling Gemini to control hardware (screen, camera) and trigger external workflows through function calling mid-conversation.

### Key Design Decisions

- **Gemini Live API (native audio-to-audio)** — Single WebSocket for input audio → spoken responses
- **No separate STT or TTS** — Gemini 2.5 Flash generates speech natively with 30 HD voices
- **No n8n for voice** — Robot connects directly to Gemini; n8n is optional for automation tasks
- **Multi-turn conversation** — Wake word starts a session; natural back-and-forth until silence timeout
- **MCP tool server** — Gemini calls tools mid-conversation (screen, camera, user-defined)
- **Hardware-agnostic** — Develop/test on desktop, deploy on Raspberry Pi or similar
- **Built-in VAD** — Gemini Live API handles voice activity detection during conversation

---

## 2. System Architecture

```
┌──────────────────────────────────────────────┐
│              Raspberry Pi / Dev Machine       │
│                                               │
│  ┌──────────────┐    ┌─────────────────────┐ │
│  │ OpenWakeWord  │───▶│  Robot Main         │ │
│  │ (always-on)   │    │  Controller         │ │
│  └──────────────┘    │  (state machine)     │ │
│                       │                      │ │
│  ┌──────────────┐    │  IDLE → CONNECTING   │ │
│  │ Audio I/O     │◀──▶│  → CONVERSATION     │ │
│  │ (mic+speaker) │    │  → IDLE             │ │
│  └──────────────┘    └──────┬──────────────┘ │
│                              │                 │
│  ┌──────────────┐    ┌──────▼──────────────┐ │
│  │ MCP Server    │◀───│ Gemini Session      │ │
│  │ (FastMCP)     │    │ Manager             │ │
│  │               │    │ (WebSocket client)  │ │
│  │ Tools:        │    └──────┬──────────────┘ │
│  │  - screen     │           │ wss://          │
│  │  - camera     │           │                 │
│  │  - user tools │           │                 │
│  └──────────────┘           │                 │
│                              │                 │
│  ┌──────────────┐           │                 │
│  │ n8n (Docker)  │           │                 │
│  │ (optional)    │           │                 │
│  └──────────────┘           │                 │
└──────────────────────────────┼─────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Google Gemini       │
                    │  Live API (Cloud)    │
                    │  2.5 Flash Native    │
                    │  Audio               │
                    └─────────────────────┘
```

### Key Differences from Previous Architecture (v2.0)

| Aspect | v2.0 (Old) | v3.0 (New) |
|--------|-----------|-----------|
| Voice engine | n8n → Gemini text + Google TTS | Gemini Live API (native audio) |
| Protocol | HTTP/SSE | WebSocket bidirectional |
| TTS | Google Cloud TTS (separate) | Gemini built-in (30 HD voices) |
| VAD | Robot-side (Silero/WebRTC) | Gemini built-in |
| Conversation | Single question/answer | Multi-turn session |
| Robot role | Thin client | Smart client |
| Function calling | Not supported | MCP tools mid-conversation |
| Latency target | ~3.3s | <1.5s |

---

## 3. Gemini Live API Integration

### 3.1 Model & Protocol

- **Model:** `gemini-2.5-flash-preview-native-audio-dialog`
- **Protocol:** WebSocket (wss://)
- **SDK:** `google-genai` Python package (Gemini Python SDK)
- **Auth:** API key for development, ephemeral tokens for production

### 3.2 Session Lifecycle

```
1. Wake word detected
2. Open WebSocket connection to Gemini
3. Send BidiGenerateContentSetup message (model, voice, system prompt, tools)
4. Receive setup confirmation
5. Begin streaming mic audio as RealtimeInput messages
6. Receive audio responses as ServerContent messages
7. Handle function calls (toolCall → execute → toolResponse)
8. Session ends on: silence timeout, explicit goodbye, error, or 15-min limit
9. For long sessions: use session resumption tokens for transparent reconnection
```

### 3.3 WebSocket Setup Message

```python
config = {
    "model": "models/gemini-2.5-flash-preview-native-audio-dialog",
    "generationConfig": {
        "responseModalities": ["AUDIO"],
        "speechConfig": {
            "voiceConfig": {
                "prebuiltVoiceConfig": {"voiceName": personality.voice}
            }
        }
    },
    "systemInstruction": {"parts": [{"text": personality.system_prompt}]},
    "tools": [mcp_session],  # MCP tools auto-discovered
    "realtimeInputConfig": {
        "automaticActivityDetection": {"disabled": False},
        "activityHandling": "START_OF_ACTIVITY_INTERRUPTS"
    },
    "inputAudioTranscription": {},
    "outputAudioTranscription": {},
    "contextWindowCompression": {"slidingWindow": {}}
}
```

### 3.4 Audio Formats

| Direction | Sample Rate | Bit Depth | Channels | Format | Chunk Size |
|-----------|------------|-----------|----------|--------|------------|
| Input (mic → Gemini) | 16 kHz | 16-bit | Mono | Raw PCM (little-endian) | 1024 bytes |
| Output (Gemini → speaker) | 24 kHz | 16-bit | Mono | Raw PCM (little-endian) | Variable |

Input and output use different sample rates — they are independent streams handled by separate pipelines. No resampling needed.

### 3.5 Session Management

- **Session duration:** ~10-minute connection lifetime, up to 15 minutes max
- **Session resumption:** Gemini provides resumption tokens for transparent reconnection
- **Context compression:** `contextWindowCompression` with `slidingWindow` enables unlimited conversation length by compressing older context
- **Concurrent sessions:** One session per robot instance

### 3.6 Built-in VAD

Gemini Live API provides automatic voice activity detection:
- Detects when user starts/stops speaking
- Configurable via `automaticActivityDetection`
- `START_OF_ACTIVITY_INTERRUPTS` — user speech interrupts Gemini's current response
- Eliminates need for robot-side VAD during conversation (only wake word detector needs to run pre-session)

### 3.7 Transcription

Both input and output audio transcription are available as side channels:
- `inputAudioTranscription` — what the user said (text)
- `outputAudioTranscription` — what Gemini said (text)
- Used for display, logging, and debugging — not part of the audio pipeline

---

## 4. Wake Word Detection

### 4.1 Implementation

- **Library:** OpenWakeWord (Apache 2.0 license, fully local)
- **Custom wake word:** Trainable for any phrase
- **Audio format:** 16 kHz / 16-bit / mono PCM (same as Gemini input — shared mic stream)
- **Always-on:** Runs continuously in IDLE state
- **Callback:** Fires `on_detected()` → triggers Gemini session setup

### 4.2 Requirements

- Detection latency: <100ms
- CPU usage: <5% when idle
- Configurable sensitivity threshold (0.0–1.0)
- Paused during active Gemini conversation (Gemini's VAD takes over)

---

## 5. Audio Pipeline

### 5.1 Capture Pipeline (Mic → Gemini)

```
Microphone → AudioInput interface → PCM frames (16kHz/16-bit/mono)
  → 1024-byte chunks → WebSocket send loop → Gemini Live API
```

- Continuous streaming while session is active
- Chunks sent as `RealtimeInput` messages
- No local VAD needed — Gemini handles activity detection
- Same mic stream shared with wake word detector (before session starts)

### 5.2 Playback Pipeline (Gemini → Speaker)

```
Gemini Live API → WebSocket receive → PCM frames (24kHz/16-bit/mono)
  → Playback buffer → AudioOutput interface → Speaker
```

- Buffer 2–3 chunks to prevent stuttering
- Support interruption (user starts speaking → stop playback immediately)
- Handle `START_OF_ACTIVITY_INTERRUPTS` — Gemini signals when user interrupts

---

## 6. Personality System

### 6.1 Gemini Voice Catalog

Gemini Live API provides 30 built-in HD voices:

| Voice | Description | Personality Fit |
|-------|-------------|-----------------|
| Achird | Friendly | Default warm assistant |
| Sulafat | Warm | Caring, empathetic |
| Puck | Upbeat | Energetic, fun |
| Zephyr | Bright | Cheerful, positive |
| Kore | Firm | Professional, authoritative |
| Charon | Informative | Educational, factual |
| Fenrir | Excitable | Enthusiastic, animated |
| Leda | Youthful | Young, casual |
| Aoede | Breezy | Relaxed, easy-going |
| Gacrux | Mature | Serious, experienced |
| Sadaltager | Knowledgeable | Expert, teacher-like |
| Vindemiatrix | Gentle | Soft, calming |
| Sadachbia | Lively | Spirited, engaging |
| Zubenelgenubi | Casual | Laid-back, informal |
| Pulcherrima | Forward | Direct, confident |
| Solaria | Crisp | Clear, articulate |
| Umbriel | Easy-going | Relaxed, approachable |
| Algieba | Smooth | Polished, refined |
| Despina | Smooth | Polished, pleasant |
| Erinome | Clear | Precise, well-spoken |
| Algenib | Gravelly | Rugged, distinctive |
| Rasalgethi | Informative | Thoughtful, measured |
| Laomedeia | Upbeat | Positive, cheerful |
| Achernar | Soft | Gentle, soothing |
| Enceladus | Breathy | Intimate, quiet |
| Iapetus | Clear | Bright, transparent |
| Callirrhoe | Easy-going | Calm, comfortable |
| Autonoe | Bright | Vivid, engaging |
| Orus | Firm | Strong, decisive |
| Schedar | Even | Balanced, steady |

### 6.2 Pre-defined Personalities

Ship with 4 curated personalities:

**1. Friendly** (default)
```json
{
  "name": "Friendly",
  "voice": "Achird",
  "system_prompt": "You are a friendly household robot named Robco. You speak naturally and warmly. Keep responses conversational and concise. You help with everyday tasks around the house.",
  "description": "Warm, conversational assistant",
  "conversation_timeout_seconds": 30,
  "vad_sensitivity": "MEDIUM"
}
```

**2. Professional**
```json
{
  "name": "Professional",
  "voice": "Kore",
  "system_prompt": "You are a professional household assistant named Robco. Be concise, factual, and efficient. Prioritize accuracy and brevity in your responses.",
  "description": "Concise, factual, business-like",
  "conversation_timeout_seconds": 20,
  "vad_sensitivity": "MEDIUM"
}
```

**3. Energetic**
```json
{
  "name": "Energetic",
  "voice": "Puck",
  "system_prompt": "You are an enthusiastic household robot named Robco! You're upbeat, fun, and love helping out. Show excitement and positivity in your responses while staying helpful.",
  "description": "Upbeat, enthusiastic, fun",
  "conversation_timeout_seconds": 30,
  "vad_sensitivity": "LOW"
}
```

**4. Calm**
```json
{
  "name": "Calm",
  "voice": "Vindemiatrix",
  "system_prompt": "You are a gentle, soothing household robot named Robco. Speak calmly and patiently. Take your time with responses and create a relaxing atmosphere.",
  "description": "Gentle, soothing, patient",
  "conversation_timeout_seconds": 45,
  "vad_sensitivity": "HIGH"
}
```

### 6.3 Custom Personalities

Users can create custom personality JSON files in `config/personalities/`:

```json
{
  "name": "My Custom Bot",
  "voice": "Leda",
  "system_prompt": "You are a fun robot who loves dad jokes...",
  "description": "Custom personality",
  "conversation_timeout_seconds": 30,
  "vad_sensitivity": "MEDIUM"
}
```

Personality is loaded into the WebSocket setup message: `voiceConfig` sets the voice, `systemInstruction` sets the system prompt.

---

## 7. Function Calling & MCP

### 7.1 Overview

Gemini Live API supports function calling mid-conversation. Tools are declared in the WebSocket setup message. When Gemini decides to call a tool, it sends a `toolCall` message, the robot executes the function and sends back a `toolResponse`, and Gemini continues speaking.

### 7.2 MCP Integration

The robot runs a local MCP server using FastMCP. The Gemini Python SDK natively connects to MCP sessions and exposes all registered tools to Gemini.

```python
from fastmcp import FastMCP

mcp = FastMCP("robco")

@mcp.tool
def display_text(text: str) -> str:
    """Show text on the robot's screen."""
    display.show(text)
    return "displayed"

@mcp.tool
def capture_camera_frame() -> Image:
    """Capture a photo from the robot's camera."""
    return camera.capture()
```

### 7.3 Function Calling Flow

```
User: "Show me what you see"
  → Audio frames sent to Gemini
  → Gemini sends toolCall: capture_camera_frame()
  → Robot captures frame, sends toolResponse with image
  → Gemini analyzes image
  → Gemini sends toolCall: display_text("I can see a cat on the couch")
  → Robot displays text on screen
  → Gemini speaks: "I can see a cat sitting on your couch!"
  → Audio frames played on speaker
```

### 7.4 Built-in Tools

- **display_text** — Show text/status on the robot's screen (Task 10)
- **capture_camera_frame** — Capture a photo for Gemini to analyze (Task 11)
- **trigger_n8n_workflow** — Fire an n8n webhook for automation (Task 12)

### 7.5 User-Extensible Tools

Users can add custom tool modules to `src/tools/user_tools/`. Any Python file with `@mcp.tool` decorators is auto-discovered and registered at startup.

---

## 8. Display Module

- Show conversation transcription (from Gemini's transcription side channel)
- Status indicators (IDLE, LISTENING, CONNECTING, etc.)
- Robot expressions/animations
- Controlled via MCP tool — Gemini can decide what to show
- Hardware-abstracted: stub for desktop testing, real display for Pi

---

## 9. Camera Module

- Frame capture for Gemini's multimodal understanding
- Gemini Live API supports inline image data alongside audio
- Controlled via MCP tool or automatic periodic capture
- Hardware-abstracted: stub returns test images, real implementation uses camera

---

## 10. n8n Integration (Optional)

n8n is **not** part of the voice pipeline. It runs optionally in Docker on the Pi for:

- Scheduled tasks (reminders, routines)
- External service integrations (smart home, weather, calendar)
- Workflow automation triggered by Gemini via function calling

The existing `server/docker-compose.yml` is preserved for this purpose. Gemini can trigger n8n workflows through the `trigger_n8n_workflow` MCP tool.

---

## 11. State Machine

```
┌──────────┐  wake word   ┌──────────────┐
│          │─────────────▶│              │
│   IDLE   │              │  CONNECTING  │
│          │◀─────────────│              │
└──────────┘   error/     └──────┬───────┘
     ▲         timeout           │
     │                    ws connected
     │                           │
     │                    ┌──────▼───────┐
     │    silence         │              │
     │    timeout /       │ CONVERSATION │
     └────goodbye /───────│              │
          error           └──────────────┘
```

**States:**
- **IDLE** — Wake word detector is listening. Mic stream feeds OpenWakeWord.
- **CONNECTING** — WebSocket opening to Gemini, sending setup message. Brief transition state (<1s).
- **CONVERSATION** — Bidirectional audio streaming active. Gemini's VAD handles turn-taking. Function calls processed. User can interrupt Gemini by speaking.
- **Back to IDLE** — On silence timeout (configurable per personality), explicit goodbye detected by Gemini, network error, or session timeout.

---

## 12. Error Handling

### 12.1 Network Failure
- Retry WebSocket connection 3x with exponential backoff
- Play cached error phrase: "I'm having trouble connecting. Please try again."

### 12.2 Session Timeout
- Gemini sessions last ~10 minutes
- Use session resumption tokens for transparent reconnection
- User doesn't notice the reconnection

### 12.3 Gemini Overloaded / Rate Limited
- Exponential backoff + retry
- Play cached phrase: "Give me a moment..."

### 12.4 Wake Word False Positive
- If no speech detected within 5s of Gemini session start, close session and return to IDLE

### 12.5 Cached Error/Status Phrases
Pre-generated at setup time using the Gemini TTS REST API (one-time generation, not the Live API). Stored locally for offline playback when the network is unavailable.

---

## 13. Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Wake word → first audio response | <1.5s | Gemini native audio eliminates STT+TTS hops |
| Turn-taking latency | <500ms | Gemini's built-in VAD + native audio generation |
| WebSocket connection setup | <1s | Including auth and setup message |
| Session resumption | <500ms | Transparent to user |
| Audio playback gap | <50ms | Between received chunks |

### Latency Comparison

| Architecture | Latency |
|-------------|---------|
| v2.0: Robot → n8n → Gemini text → Google TTS → Robot | ~3.3s |
| **v3.0: Robot → Gemini Live API (native audio)** | **<1.5s** |
| Improvement | **~55% faster** |

---

## 14. Cost

### Development Phase
- Gemini 2.5 Flash native audio preview: **Free** during preview period
- No separate TTS costs (Gemini generates speech)
- **Total: $0/month**

### Production Phase (Post-Preview)
- Input audio tokens: $3 per 1M tokens
- Output audio tokens: $12 per 1M tokens
- 10-second utterance ≈ 320 tokens
- 100 interactions/day ≈ 64K tokens/day ≈ 1.9M tokens/month
- **Estimated: $5–10/month for hobby use**

### Compared to v2.0
- Eliminated Google Cloud TTS costs entirely
- Single service to manage billing
- No n8n server costs for voice

---

## 15. Security

### API Key Management
- Store all API keys in `.env` (never committed)
- Ephemeral tokens for production (short-lived, refreshed automatically)
- Rotate keys every 90 days

### Network Security
- WebSocket connection uses TLS (wss://)
- No ports exposed on the local network for voice (outbound-only)
- n8n (if used) secured with API key auth

### Privacy
- Audio streamed to Google Cloud for processing
- No persistent storage of audio on Google's side (per Gemini API terms)
- Transcription available locally for logging/display
- Option to disable transcription logging

---

## 16. Deployment

### Software Stack
- **OS:** Raspberry Pi OS / Ubuntu / macOS (dev)
- **Runtime:** Python 3.9+
- **Key libraries:**
  - `google-genai` — Gemini Python SDK (Live API client)
  - `openwakeword` — Wake word detection
  - `fastmcp` — MCP tool server
  - `numpy` — Audio buffer manipulation
  - `pyyaml` — Configuration loading
  - `sounddevice` / hardware-specific (in impl/ only)

### Hardware Requirements (Development)
- Any machine with mic + speaker
- Python 3.9+
- Internet connection

### Hardware Requirements (Production — TBD)
- Raspberry Pi 4/5 or equivalent ARM SBC
- USB or I2S microphone
- Speaker (3.5mm, I2S, or USB)
- Optional: display (SPI/HDMI), camera (USB/CSI)
- WiFi or Ethernet

---

## Document Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2026-02-06 | 1.0 | Initial draft — voice pipeline with n8n + Gemini text + Google TTS |
| 2026-02-06 | 2.0 | All-Google architecture: Gemini native audio input + Google Cloud TTS |
| 2026-02-08 | 3.0 | **Major redesign:** Gemini Live API native audio-to-audio, WebSocket, multi-turn conversation, MCP tools, no separate TTS, no n8n for voice |

---

**END OF DOCUMENT**
