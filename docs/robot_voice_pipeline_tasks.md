# Robco Voice Robot — Task Breakdown

**Source:** `robot_voice_pipeline_design.md` v3.0
**Architecture:** Gemini Live API — native audio-to-audio via WebSocket
**Purpose:** Each task is a self-contained unit of work for Claude Code. Tasks define inputs, outputs, and interface contracts so independently-built pieces plug together cleanly.

> **Hardware note:** Robot hardware is TBD. All code uses abstract hardware interfaces (Task 2) with desktop stubs. Tests never require real hardware.

> **Architecture note:** The robot connects directly to Gemini via WebSocket. There is no n8n middleware for voice. n8n is optional, used only for automation workflows (Task 12).

---

## Dependency Graph

```
Phase 1: Foundations
  Task 1: Project Scaffold & Config System
  Task 2: Hardware Abstraction Layer ──────┐
  Task 3: Personality Configuration ───────┤
                                           │
Phase 2: Core Voice Pipeline               │
  Task 4: Gemini Session Manager ──────────┤
  Task 5: Audio Capture Pipeline ──────────┤
  Task 6: Audio Playback Pipeline ─────────┤
  Task 7: Wake Word Detection ─────────────┤
                                           │
Phase 3: Robot Assembly                    │
  Task 8: Robot Main Controller ◀──────────┘
           (connects 4+5+6+7)
           │
           ▼  Working voice robot!

Phase 4: Extensibility
  Task 9:  MCP Tool Server
  Task 10: Display Module
  Task 11: Camera Module

Phase 5: Optional
  Task 12: n8n Integration

Phase 6: Hardening
  Task 13: Error Handling & Reconnection
  Task 14: Logging & Monitoring
  Task 15: CLI Test Client & E2E Tests
```

---

## Task 1 — Project Scaffold & Config System

**Goal:** Set up the repository structure, configuration loading, environment variable management, and Python packaging.

**What to build:**

- Directory structure:
  ```
  src/
    core/
      config.py              # Settings loader
      state_machine.py       # State enum + transitions (Task 8)
      controller.py          # Robot main controller (Task 8)
    gemini/
      session.py             # Live API WebSocket client (Task 4)
      audio_handler.py       # Audio frame send/receive (Tasks 5, 6)
    hardware/
      interfaces.py          # ABCs: AudioInput, AudioOutput, Display, Camera (Task 2)
      stubs.py               # Desktop stub implementations (Task 2)
      impl/                  # Real hardware implementations (future)
    wake_word/
      detector.py            # OpenWakeWord integration (Task 7)
    audio/
      capture.py             # Mic → PCM pipeline (Task 5)
      playback.py            # PCM → speaker pipeline (Task 6)
    tools/
      server.py              # FastMCP server setup (Task 9)
      display.py             # Display MCP tool (Task 10)
      camera.py              # Camera MCP tool (Task 11)
      user_tools/            # User-added tool modules (Task 9)
    personality/
      manager.py             # Personality loader + catalog (Task 3)
      voices.py              # 30-voice catalog with descriptions (Task 3)
  config/
    default.yaml             # Default config values
    personalities/           # Personality JSON files (Task 3)
  server/                    # n8n (optional, Task 12) — existing files kept
    docker-compose.yml
    workflows/
  scripts/
    generate_phrases.py      # Generate cached error/status phrases (Task 13)
    test_client.py           # CLI test client (Task 15)
    setup_n8n.sh             # n8n setup (Task 12)
  tests/
    fixtures/
    test_*.py
  ```

- `src/core/config.py` — single source of truth for all configuration. Loads from `.env` and `config/default.yaml`. Validates required keys.
- `config/default.yaml` — default configuration values.
- `.env.example` — template with all environment variables.
- `requirements.txt` — Python dependencies.

**Interface contract:**
```python
# src/core/config.py
@dataclass(frozen=True)
class Settings:
    # Gemini
    gemini_api_key: str
    gemini_model: str               # default: "gemini-2.5-flash-preview-native-audio-dialog"

    # Audio
    input_sample_rate: int          # default: 16000
    output_sample_rate: int         # default: 24000
    input_channels: int             # default: 1
    audio_chunk_size: int           # default: 1024

    # Wake word
    wake_word: str                  # default: "hey robot"
    wake_word_sensitivity: float    # default: 0.5

    # Personality
    default_personality: str        # default: "friendly"
    personalities_dir: str          # default: "config/personalities"

    # Conversation
    conversation_timeout: int       # default: 30 (seconds of silence before ending)
    max_session_duration: int       # default: 600 (10 minutes)

    # n8n (optional)
    n8n_server_url: str             # default: "" (empty = disabled)
    n8n_api_key: str                # default: ""

    # Logging
    log_level: str                  # default: "INFO"

def load_settings() -> Settings: ...
```

**Outputs:** Repository skeleton, config loader, `.env.example`, `requirements.txt`, `config/default.yaml`.

**Depends on:** Nothing.

**Consumed by:** All subsequent tasks.

---

## Task 2 — Hardware Abstraction Layer

**Goal:** Define abstract interfaces for all hardware I/O (audio, display, camera) and provide desktop stub implementations for testing.

**What to build:**
- `src/hardware/interfaces.py` — abstract base classes for all hardware
- `src/hardware/stubs.py` — desktop stub implementations (file-based audio, terminal display, static image camera)

**Interface contract:**
```python
# src/hardware/interfaces.py

class AudioInput(ABC):
    """Abstract microphone input."""

    @abstractmethod
    def open_stream(self, sample_rate: int = 16000, channels: int = 1,
                    chunk_size: int = 1024) -> None:
        """Open the audio input stream."""
        ...

    @abstractmethod
    def read_chunk(self) -> bytes:
        """Read one chunk of PCM audio data."""
        ...

    @abstractmethod
    def close_stream(self) -> None:
        """Close the audio input stream."""
        ...

    @abstractmethod
    def is_open(self) -> bool:
        """Check if the stream is currently open."""
        ...


class AudioOutput(ABC):
    """Abstract speaker output."""

    @abstractmethod
    def open_stream(self, sample_rate: int = 24000, channels: int = 1) -> None:
        """Open the audio output stream."""
        ...

    @abstractmethod
    def write_chunk(self, data: bytes) -> None:
        """Write one chunk of PCM audio data to the speaker."""
        ...

    @abstractmethod
    def close_stream(self) -> None:
        """Close the audio output stream."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Immediately stop playback and close the stream."""
        ...

    @abstractmethod
    def is_open(self) -> bool:
        """Check if the stream is currently open."""
        ...


class DisplayOutput(ABC):
    """Abstract display/screen output."""

    @abstractmethod
    def show_text(self, text: str) -> None:
        """Display text on the screen."""
        ...

    @abstractmethod
    def show_status(self, status: str) -> None:
        """Display a status indicator."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear the display."""
        ...


class CameraInput(ABC):
    """Abstract camera input."""

    @abstractmethod
    def capture_frame(self) -> bytes:
        """Capture a single frame as JPEG bytes."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if camera hardware is available."""
        ...
```

**Stub implementations:**
- `StubAudioInput` — reads from a WAV file, returns chunks of PCM data
- `StubAudioOutput` — writes PCM data to a WAV file
- `StubDisplayOutput` — prints to terminal
- `StubCameraInput` — returns a static test JPEG from `tests/fixtures/`

**Outputs:** `src/hardware/interfaces.py`, `src/hardware/stubs.py`.

**Depends on:** Nothing.

**Consumed by:** Tasks 5, 6, 7, 8, 10, 11.

---

## Task 3 — Personality Configuration

**Goal:** Implement the personality system — voice catalog, personality JSON loading, and pre-defined personalities.

**What to build:**
- `src/personality/voices.py` — catalog of all 30 Gemini voices with descriptions
- `src/personality/manager.py` — loads/validates personality JSON files, provides personality lookup
- `config/personalities/friendly.json` — default personality
- `config/personalities/professional.json`
- `config/personalities/energetic.json`
- `config/personalities/calm.json`

**Interface contract:**
```python
# src/personality/voices.py
@dataclass(frozen=True)
class VoiceInfo:
    name: str           # e.g., "Achird"
    description: str    # e.g., "Friendly"
    personality_fit: str # e.g., "Default warm assistant"

VOICE_CATALOG: dict[str, VoiceInfo] = { ... }  # All 30 voices

def get_voice(name: str) -> VoiceInfo: ...
def list_voices() -> list[VoiceInfo]: ...


# src/personality/manager.py
@dataclass(frozen=True)
class PersonalityConfig:
    name: str
    voice: str                          # Gemini voice name (e.g., "Achird")
    system_prompt: str
    description: str
    conversation_timeout_seconds: int   # default: 30
    vad_sensitivity: str                # "LOW" | "MEDIUM" | "HIGH"

class PersonalityManager:
    def __init__(self, personalities_dir: str): ...
    def get_personality(self, name: str) -> PersonalityConfig: ...
    def list_personalities(self) -> list[str]: ...
    def get_default(self) -> PersonalityConfig: ...
```

**Personality JSON schema:**
```json
{
  "name": "Friendly",
  "voice": "Achird",
  "system_prompt": "You are a friendly household robot named Robco...",
  "description": "Warm, conversational assistant",
  "conversation_timeout_seconds": 30,
  "vad_sensitivity": "MEDIUM"
}
```

**Outputs:** Voice catalog, personality manager, 4 personality JSON files.

**Depends on:** Task 1 (config paths).

**Consumed by:** Tasks 4, 8.

---

## Task 4 — Gemini Live API Session Manager

**Goal:** Build the WebSocket client that manages Gemini Live API sessions — connection, setup, audio streaming, function call handling, and session lifecycle.

This is the core of the new architecture. The session manager wraps the `google-genai` SDK's Live API client.

**What to build:**
- `src/gemini/session.py` — session lifecycle management

**Interface contract:**
```python
# src/gemini/session.py
from google import genai

class GeminiSessionConfig:
    """Configuration for a Gemini Live session."""
    model: str
    voice: str
    system_prompt: str
    tools: list          # MCP tools (empty list if none)
    vad_sensitivity: str # "LOW" | "MEDIUM" | "HIGH"

class GeminiSession:
    def __init__(self, api_key: str, config: GeminiSessionConfig): ...

    async def connect(self) -> None:
        """Open WebSocket connection and send setup message."""
        ...

    async def send_audio(self, chunk: bytes) -> None:
        """Send a chunk of PCM audio to Gemini."""
        ...

    async def receive(self) -> AsyncIterator[ServerMessage]:
        """Yield messages from Gemini (audio chunks, transcription, tool calls, etc.)."""
        ...

    async def send_tool_response(self, call_id: str, result: dict) -> None:
        """Send the result of a function call back to Gemini."""
        ...

    async def close(self) -> None:
        """Close the WebSocket session gracefully."""
        ...

    @property
    def is_connected(self) -> bool: ...

@dataclass
class ServerMessage:
    type: str               # "audio" | "transcription" | "tool_call" | "turn_complete" | "error"
    audio_data: bytes       # PCM audio (for type="audio")
    text: str               # Transcription text or error message
    tool_call_id: str       # For function calls
    tool_name: str          # For function calls
    tool_args: dict         # For function calls
```

**Key implementation details:**
- Uses `google-genai` SDK: `client.aio.live.connect(model=..., config=...)`
- Setup includes: model, voice config, system instruction, tools, VAD config, transcription, context compression
- Handles session resumption tokens for reconnection
- Async/await pattern — all I/O is non-blocking

**Depends on:** Task 1 (config), Task 3 (personality config).

**Consumed by:** Tasks 5, 6, 8.

---

## Task 5 — Audio Capture Pipeline

**Goal:** Stream microphone audio to the Gemini session as PCM chunks.

**What to build:**
- `src/audio/capture.py` — reads from AudioInput, sends chunks to GeminiSession

**Interface contract:**
```python
# src/audio/capture.py
class AudioCaptureStream:
    def __init__(self, audio_input: AudioInput, session: GeminiSession,
                 sample_rate: int = 16000, chunk_size: int = 1024): ...

    async def start(self) -> None:
        """Begin capturing and sending audio chunks to Gemini."""
        ...

    async def stop(self) -> None:
        """Stop capturing audio."""
        ...

    @property
    def is_streaming(self) -> bool: ...
```

**Behavior:**
- Opens AudioInput stream at 16kHz/16-bit/mono
- Reads chunks in a loop, sends each to `session.send_audio(chunk)`
- Runs as an asyncio task alongside the receive loop
- Stops on: session close, explicit stop, or error

**Depends on:** Task 2 (AudioInput), Task 4 (GeminiSession).

**Consumed by:** Task 8.

---

## Task 6 — Audio Playback Pipeline

**Goal:** Receive audio from the Gemini session and play it through the speaker.

**What to build:**
- `src/audio/playback.py` — receives audio from GeminiSession, plays through AudioOutput

**Interface contract:**
```python
# src/audio/playback.py
class AudioPlaybackStream:
    def __init__(self, audio_output: AudioOutput,
                 sample_rate: int = 24000, buffer_chunks: int = 3): ...

    async def play_chunk(self, audio_data: bytes) -> None:
        """Buffer and play a chunk of PCM audio."""
        ...

    async def play_file(self, file_path: str) -> None:
        """Play a local audio file (for cached error phrases)."""
        ...

    def stop(self) -> None:
        """Immediately stop playback (for interruption)."""
        ...

    @property
    def is_playing(self) -> bool: ...
```

**Behavior:**
- Opens AudioOutput stream at 24kHz/16-bit/mono
- Buffers 2–3 chunks before starting playback to prevent stuttering
- Supports immediate interruption (user starts speaking)
- Can also play local WAV/PCM files (for cached error phrases)

**Depends on:** Task 2 (AudioOutput), Task 4 (GeminiSession provides audio chunks).

**Consumed by:** Task 8.

---

## Task 7 — Wake Word Detection

**Goal:** Implement always-on wake word detection using OpenWakeWord.

**What to build:**
- `src/wake_word/detector.py` — OpenWakeWord integration

**Interface contract:**
```python
# src/wake_word/detector.py
class WakeWordDetector:
    def __init__(self, audio_input: AudioInput,
                 wake_word: str = "hey robot",
                 sensitivity: float = 0.5): ...

    async def start(self, on_detected: Callable[[], Awaitable[None]]) -> None:
        """Begin listening for the wake word. Calls on_detected() when triggered."""
        ...

    def stop(self) -> None:
        """Stop listening for the wake word."""
        ...

    def pause(self) -> None:
        """Temporarily pause detection (during active Gemini session)."""
        ...

    def resume(self) -> None:
        """Resume detection after pause."""
        ...

    @property
    def is_listening(self) -> bool: ...
```

**Behavior:**
- Continuously reads PCM audio from AudioInput at 16kHz
- Feeds frames to OpenWakeWord model
- Fires callback on detection
- Paused during active Gemini conversation (Gemini's VAD handles turn-taking)
- Resumed when conversation ends (back to IDLE)

**Acceptance criteria:**
- With stub AudioInput (feeding WAV file), detects wake word and fires callback
- CPU usage <5% when idle
- Detection latency <100ms

**Depends on:** Task 2 (AudioInput), Task 1 (settings).

**Consumed by:** Task 8.

---

## Task 8 — Robot Main Controller

**Goal:** Orchestrate the full robot interaction as a state machine. This ties together all components into a working voice robot.

**What to build:**
- `src/core/state_machine.py` — state enum and transition logic
- `src/core/controller.py` — the main controller

**Interface contract:**
```python
# src/core/state_machine.py
from enum import Enum, auto

class RobotState(Enum):
    IDLE = auto()          # Wake word detector listening
    CONNECTING = auto()    # Opening Gemini WebSocket
    CONVERSATION = auto()  # Bidirectional audio streaming
    SHUTTING_DOWN = auto() # Graceful shutdown

# src/core/controller.py
class RobotController:
    def __init__(self, settings: Settings,
                 audio_input: AudioInput,
                 audio_output: AudioOutput,
                 display: DisplayOutput | None = None,
                 camera: CameraInput | None = None): ...

    async def start(self) -> None:
        """Begin the main loop (wake word → conversation → idle)."""
        ...

    async def stop(self) -> None:
        """Graceful shutdown."""
        ...

    @property
    def state(self) -> RobotState: ...
```

**State machine behavior:**

1. **IDLE:**
   - Wake word detector running
   - On wake word detected → transition to CONNECTING

2. **CONNECTING:**
   - Load personality config
   - Open Gemini WebSocket session
   - On connected → transition to CONVERSATION
   - On error → play cached error phrase, return to IDLE

3. **CONVERSATION:**
   - Start audio capture stream (mic → Gemini)
   - Start audio playback stream (Gemini → speaker)
   - Handle incoming messages:
     - `audio` → play through speaker
     - `transcription` → display on screen (if available)
     - `tool_call` → execute via MCP server, send response
     - `turn_complete` → reset silence timer
   - On silence timeout (configurable per personality) → close session, return to IDLE
   - On error → play cached error phrase, return to IDLE
   - User interruption: Gemini handles via `START_OF_ACTIVITY_INTERRUPTS`

4. **SHUTTING_DOWN:**
   - Close Gemini session
   - Stop wake word detector
   - Close audio streams

**Depends on:** Tasks 1, 2, 3, 4, 5, 6, 7.

**Consumed by:** Standalone entry point. `python -m src.core.controller` runs the robot.

---

## Task 9 — MCP Tool Server

**Goal:** Set up the FastMCP server that exposes tools to Gemini for function calling during conversation.

**What to build:**
- `src/tools/server.py` — FastMCP server setup, tool registration, user tool discovery

**Interface contract:**
```python
# src/tools/server.py
from fastmcp import FastMCP

class ToolServer:
    def __init__(self): ...

    def register_builtin_tools(self, display: DisplayOutput | None = None,
                                camera: CameraInput | None = None) -> None:
        """Register built-in tools (display, camera) based on available hardware."""
        ...

    def discover_user_tools(self, tools_dir: str = "src/tools/user_tools") -> None:
        """Auto-discover and register user tool modules from a directory."""
        ...

    def get_mcp_session(self):
        """Return the MCP session for passing to Gemini setup."""
        ...

    @property
    def registered_tools(self) -> list[str]: ...
```

**Built-in tools registered:**
- `display_text(text: str)` — if DisplayOutput is available
- `display_status(status: str)` — if DisplayOutput is available
- `capture_camera_frame()` — if CameraInput is available

**User tool discovery:**
- Scans `src/tools/user_tools/` for Python files
- Each file can define `@mcp.tool` decorated functions
- Auto-registered at startup

**Depends on:** Task 2 (hardware interfaces), Task 4 (GeminiSession accepts tools).

**Consumed by:** Task 8 (controller passes tools to Gemini session).

---

## Task 10 — Display Module

**Goal:** MCP tool that controls the robot's display for showing transcription, status, and expressions.

**What to build:**
- `src/tools/display.py` — MCP tools for display control

**Interface contract:**
```python
# src/tools/display.py
# These are registered as MCP tools via the ToolServer

def display_text(text: str) -> str:
    """Show text on the robot's screen. Returns confirmation."""
    ...

def display_status(status: str) -> str:
    """Show a status indicator (e.g., 'listening', 'thinking'). Returns confirmation."""
    ...

def clear_display() -> str:
    """Clear the screen. Returns confirmation."""
    ...
```

**Also implements:**
- Automatic transcription display (subscribes to Gemini's transcription side channel)
- State-based status indicator (shows current RobotState)

**Depends on:** Task 2 (DisplayOutput interface), Task 9 (MCP server).

**Consumed by:** Task 8 (controller integrates display updates).

---

## Task 11 — Camera Module

**Goal:** MCP tool that captures camera frames for Gemini's multimodal understanding.

**What to build:**
- `src/tools/camera.py` — MCP tool for camera capture

**Interface contract:**
```python
# src/tools/camera.py
# Registered as MCP tool via the ToolServer

def capture_camera_frame() -> dict:
    """Capture a photo from the robot's camera.
    Returns: {"image": <base64 JPEG>, "width": int, "height": int}
    """
    ...
```

**Behavior:**
- Captures a single frame via CameraInput interface
- Returns JPEG bytes (base64 encoded for Gemini)
- Gemini can call this tool mid-conversation to "see" things
- Stub implementation returns a static test image

**Depends on:** Task 2 (CameraInput interface), Task 9 (MCP server).

**Consumed by:** Gemini function calling during conversation.

---

## Task 12 — n8n Integration (Optional)

**Goal:** Enable Gemini to trigger n8n workflows via function calling for automation tasks.

**What to build:**
- MCP tool: `trigger_n8n_workflow` — calls n8n webhook endpoint
- Keep existing `server/docker-compose.yml` and `scripts/setup_n8n.sh`

**Interface contract:**
```python
# Added as MCP tool
def trigger_n8n_workflow(workflow_name: str, data: dict) -> dict:
    """Trigger an n8n workflow via webhook.
    Args:
        workflow_name: Name/path of the n8n webhook to trigger
        data: JSON payload to send to the workflow
    Returns: Response from n8n workflow
    """
    ...
```

**Behavior:**
- POSTs to `{n8n_server_url}/webhook/{workflow_name}` with JSON payload
- Only available if `n8n_server_url` is configured in settings
- Timeout: 30 seconds
- Gemini can decide to trigger workflows during conversation (e.g., "turn on the lights" → triggers smart home workflow)

**Depends on:** Task 1 (config for n8n URL), Task 9 (MCP server).

**Consumed by:** Gemini function calling during conversation.

---

## Task 13 — Error Handling & Reconnection

**Goal:** Implement robust error handling for network failures, session timeouts, and Gemini errors.

**What to build:**
- Add to `src/gemini/session.py`:
  - WebSocket reconnection with exponential backoff (3 retries)
  - Session resumption using Gemini's resumption tokens
  - Rate limit handling (429 responses)
- Add to `src/core/controller.py`:
  - Error state transitions (any error → play cached phrase → IDLE)
  - Wake word false positive handling (no speech within 5s → close session)
- `scripts/generate_phrases.py`:
  - Generates cached error/status audio phrases using Gemini TTS REST API
  - Phrases: "I'm having trouble connecting", "Give me a moment", etc.
  - Stored in `cache/phrases/` for offline playback

**Cached phrase list:**
```python
ERROR_PHRASES = {
    "connection_error": "I'm having trouble connecting. Please try again.",
    "timeout": "Give me a moment, I'm taking longer than usual.",
    "no_speech": "I didn't catch that. Could you try again?",
    "general_error": "Something went wrong. Let me try again.",
    "goodbye": "Goodbye! Let me know if you need anything.",
}
```

**Depends on:** Tasks 4, 8.

**Consumed by:** All runtime paths.

---

## Task 14 — Logging & Monitoring

**Goal:** Implement structured logging and per-session metrics.

**What to build:**
- `src/core/logging.py` — centralized logging configuration
- Per-session metrics:
  - Session ID, start time, duration
  - Wake word → first audio response latency
  - Number of turns in conversation
  - Tool calls made
  - Errors encountered
  - Estimated token usage / cost

**Interface contract:**
```python
# src/core/logging.py
def setup_logging(level: str = "INFO") -> None:
    """Configure logging for all modules."""
    ...

class SessionMetrics:
    session_id: str
    start_time: float
    first_response_latency_ms: float
    turn_count: int
    tool_calls: list[str]
    errors: list[str]
    estimated_tokens: int

    def log_summary(self) -> None:
        """Log a summary of the session metrics."""
        ...
```

**Depends on:** Task 1 (config for log level).

**Consumed by:** All modules.

---

## Task 15 — CLI Test Client & E2E Tests

**Goal:** Desktop test client for exercising the full pipeline and a pytest suite.

**What to build:**
- `scripts/test_client.py`:
  - Records from laptop mic (using sounddevice)
  - Connects to Gemini Live API directly (same as robot)
  - Plays responses on laptop speakers
  - Supports `--file input.wav` mode
  - Supports `--personality` selection
  - Prints transcription and latency

- `tests/test_e2e.py`:
  - Uses stub hardware with sample WAV files
  - Tests complete flow: wake word → Gemini session → audio playback
  - Mocks Gemini WebSocket for offline testing
  - Asserts latency targets (<1.5s for local processing overhead)

```bash
# Interactive mode
python scripts/test_client.py --personality friendly

# File mode
python scripts/test_client.py --file tests/fixtures/hello.wav --personality professional
```

**Depends on:** All tasks (full integration test).

**Consumed by:** Developer testing, CI.

---

## Implementation Order

| Phase | Tasks | What You Get |
|-------|-------|-------------|
| **1. Foundations** | 1, 2, 3 | Repo structure, config, hardware stubs, personality system |
| **2. Core Voice** | 4, 5, 6, 7 | Gemini session, audio I/O pipelines, wake word |
| **3. Assembly** | 8 | **Working voice robot!** (with stubs) |
| **4. Extensibility** | 9, 10, 11 | MCP tools, display, camera |
| **5. Optional** | 12 | n8n integration |
| **6. Hardening** | 13, 14, 15 | Error handling, logging, testing |

After Task 8, you have a **functional voice robot** that can be tested on desktop with stubs or real hardware.

---

## Notes for Claude Code Sessions

- **One task per session.** Start by reading `docs/PROGRESS.md` for current state.
- **Always run tests** before marking a task complete.
- **Interface contracts are binding.** If you need to change one, note it in PROGRESS.md and list affected downstream tasks.
- **Hardware is TBD.** Never import hardware-specific libraries outside `src/hardware/impl/`.
- **Gemini Live API is the voice engine.** No standalone TTS or STT calls for the voice pipeline.
- **Async/await pattern.** The Gemini SDK uses asyncio. All I/O-bound code should be async.
- **Environment variables.** Never hardcode API keys. Load from `.env` via config system.
