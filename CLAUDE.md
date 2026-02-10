# CLAUDE.md — Project Rules & Context

This file is read by Claude Code at the start of each session. It contains project context, architectural rules, and coding conventions.

## Project Overview

Robco is a voice-interactive household robot powered by Google Gemini's Live API. The robot detects a wake word, opens a WebSocket session to Gemini, and engages in natural multi-turn conversation with bidirectional audio streaming. Gemini handles speech understanding, reasoning, and speech generation natively — no separate STT or TTS services needed.

The architecture is extensible via MCP (Model Context Protocol) tools, enabling Gemini to control hardware (screen, camera) and trigger external workflows through function calling mid-conversation.

Key components:
1. **Robot device** — wake word detection, audio I/O, state machine, MCP tool server (Python)
2. **Gemini Live API** — native audio-to-audio via WebSocket (cloud)
3. **n8n (optional)** — workflow automation triggered by Gemini via function calling (Docker)

## Key Documents

- `docs/robot_voice_pipeline_design.md` — Full technical architecture (v3.0). Source of truth for system design, data flow, API formats, error handling, and performance targets.
- `docs/robot_voice_pipeline_tasks.md` — 15 atomic tasks with dependency graph, interface contracts, and implementation order. Source of truth for what to build and in what order.
- `docs/PROGRESS.md` — Tracks task status, decisions, interface changes, and session-by-session work log. Update this at the end of every session.

## Architectural Rules

These are non-negotiable constraints. Do not deviate without explicit user approval.

1. **Gemini Live API is the voice engine.** The robot connects directly to Gemini via WebSocket for all voice interaction. No separate STT or TTS services for the voice pipeline. The only exception is `scripts/generate_phrases.py`, which uses the Gemini TTS REST API for one-time cached phrase generation.

2. **Hardware abstraction is mandatory.** All robot-side code that touches microphones, speakers, displays, cameras, or GPIO must go through the abstract interfaces in `src/hardware/`. Never import hardware-specific libraries (pyaudio, sounddevice, RPi.GPIO, picamera, etc.) outside of `src/hardware/impl/` directories.

3. **The robot is a smart client.** The robot runs the Gemini SDK, MCP tool server, wake word detection, and audio I/O. It connects directly to Gemini — no middleware server for voice.

4. **WebSocket bidirectional streaming.** Audio flows bidirectionally over a single WebSocket connection. Input audio (mic) streams continuously to Gemini. Output audio (speaker) streams back from Gemini. Do not buffer entire responses before playback.

5. **Async/await pattern.** The Gemini SDK uses asyncio. All I/O-bound code must be async. Use `asyncio.Task` for concurrent operations (audio send/receive loops).

6. **One task per session.** Each Claude Code session should focus on one task from the task breakdown. Start by reading `docs/PROGRESS.md` to find the current task, then read the task spec in `docs/robot_voice_pipeline_tasks.md`.

## Coding Conventions

### Python
- **Version:** Python 3.9+ (use `from __future__ import annotations` if needed for newer typing syntax)
- **Type hints:** Required on all function signatures. Use `typing` module types.
- **Dataclasses:** Use `@dataclass` for data containers. Use `@dataclass(frozen=True)` for immutable config objects.
- **Abstract classes:** Use `abc.ABC` and `@abstractmethod` for hardware interfaces and any other extension points.
- **Naming:** snake_case for functions/variables, PascalCase for classes, UPPER_SNAKE for constants.
- **Docstrings:** Required on all public classes and methods. Google-style docstrings.
- **Imports:** Standard library first, third-party second, project imports third. Separate groups with blank lines.
- **Error handling:** Raise specific exceptions, not bare `Exception`. Define project-specific exceptions when appropriate.
- **Async:** Use `async def` for I/O-bound functions. Use `asyncio.create_task()` for concurrent operations.

### Testing
- **Framework:** pytest (with pytest-asyncio for async tests)
- **Location:** `tests/` directory, mirroring source structure (e.g., `tests/test_capture.py`)
- **Hardware:** Always use stub implementation (`src/hardware/stubs.py`) — tests must never require real microphones, speakers, displays, or cameras.
- **External services:** Mock Gemini WebSocket connections. Tests must work offline.

## Project Structure

```
src/
  core/
    config.py              # Settings loader (Task 1)
    state_machine.py       # Robot controller states (Task 8)
    controller.py          # Robot main controller (Task 8)
  gemini/
    session.py             # Live API WebSocket client (Task 4)
  hardware/
    interfaces.py          # ABC: AudioInput, AudioOutput, DisplayOutput, CameraInput (Task 2)
    stubs.py               # Desktop stub implementations (Task 2)
    impl/                  # Real hardware implementations (future)
  wake_word/
    detector.py            # OpenWakeWord integration (Task 7)
  audio/
    capture.py             # Mic → Gemini PCM pipeline (Task 5)
    playback.py            # Gemini → speaker PCM pipeline (Task 6)
  tools/
    server.py              # FastMCP server setup (Task 9)
    display.py             # Display MCP tool (Task 10)
    camera.py              # Camera MCP tool (Task 11)
    user_tools/            # User-added tool modules (Task 9)
  personality/
    manager.py             # Personality loader + catalog (Task 3)
    voices.py              # 30-voice catalog with descriptions (Task 3)
config/
  default.yaml             # Default config values (Task 1)
  personalities/           # Personality JSON files (Task 3)
    friendly.json
    professional.json
    energetic.json
    calm.json
server/                    # n8n (optional, Task 12)
  docker-compose.yml
  workflows/
scripts/
  generate_phrases.py      # Generate cached error/status phrases (Task 13)
  test_client.py           # CLI test client (Task 15)
  setup_n8n.sh             # n8n setup (Task 12)
tests/
  fixtures/                # Test audio files, sample data
  test_*.py
```

## Environment Variables & Secrets

Never hardcode API keys, passwords, or server URLs. All secrets and environment-specific values go in `.env` (not committed) and are loaded through `src/core/config.py`.

`.env.example` must be kept in sync with all required environment variables.

Required variables:
- `GEMINI_API_KEY` — Google Gemini API key (used by robot to connect to Live API)
- `GEMINI_MODEL` — Model name (default: `gemini-2.5-flash-preview-native-audio-dialog`)

Optional variables:
- `WAKE_WORD` — Wake word string (default: "hey robot")
- `WAKE_WORD_SENSITIVITY` — Detection sensitivity 0.0–1.0 (default: 0.5)
- `DEFAULT_PERSONALITY` — Default personality name (default: "friendly")
- `CONVERSATION_TIMEOUT` — Seconds of silence before ending session (default: 30)
- `MAX_SESSION_DURATION` — Max session length in seconds (default: 600)
- `N8N_SERVER_URL` — n8n server URL, empty to disable (default: "")
- `N8N_API_KEY` — n8n API key (default: "")
- `LOG_LEVEL` — Logging level: DEBUG/INFO/WARN/ERROR (default: INFO)

## Interface Contracts

The task breakdown (`docs/robot_voice_pipeline_tasks.md`) defines interface contracts for each module. These are binding. If you need to change an interface during implementation:
1. Note the change in `docs/PROGRESS.md` under "Interface Change Log"
2. List which downstream tasks are affected
3. Update affected task implementations if they have already been completed

## Session Workflow

At the start of each session:
1. Read `docs/PROGRESS.md` to understand current state and find the next task
2. Read the relevant task spec in `docs/robot_voice_pipeline_tasks.md`
3. Verify prerequisite tasks are complete (check PROGRESS.md)
4. Implement the task following the interface contract
5. Write tests and verify all tests pass
6. Update `docs/PROGRESS.md`: mark task status, fill in details, add a session log entry

## Constraints & Gotchas

- **Hardware is TBD.** The robot hardware has not been selected. All robot code must work with the stub implementation.
- **Free tier awareness.** Gemini 2.5 Flash native audio is free during preview. Do not add services that incur costs during development.
- **Audio formats.** Robot captures at 16kHz/16-bit/mono PCM. Gemini outputs at 24kHz/16-bit/mono PCM. These are independent streams — no resampling needed.
- **WebSocket protocol.** The Gemini Live API uses WebSocket with specific message types (RealtimeInput, ServerContent, ToolCall, ToolResponse). See design doc section 3 for details.
- **Gemini SDK.** Use the `google-genai` Python package, not the older `google-generativeai` package. The Live API is accessed via `client.aio.live.connect()`.
- **n8n is optional.** The `server/` directory contains n8n Docker setup for optional automation workflows. It is NOT part of the voice pipeline.
- **Existing server files.** `server/docker-compose.yml`, `server/workflows/voice-pipeline.json`, and `scripts/setup_n8n.sh` are from the old architecture. They're kept for optional n8n integration (Task 12) — do not delete them.
