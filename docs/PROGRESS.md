# Robco Voice Robot — Project Progress

**Last Updated:** 2026-02-10
**Current Phase:** 5 — Optional / 6 — Hardening
**Overall Status:** Phase 4 Complete — Extensible voice robot with MCP tools!

---

## Project Summary

| Metric | Value |
|--------|-------|
| Tasks Complete | 11 / 15 |
| Current Phase | 5 — Optional / 6 — Hardening |
| Blocking Issues | None |
| Next Task | Task 12 — n8n Integration (optional) or Task 13 — Error Handling |

---

## Task Status

### Phase 1: Foundations

#### Task 1 — Project Scaffold & Config System
- **Status:** Complete
- **Files:** `src/core/config.py`, `config/default.yaml`, `requirements.txt`, all `__init__.py` files
- **What was built:** Full directory structure (`src/` with 9 subpackages), `Settings` frozen dataclass, `load_settings()` with env > yaml > hardcoded default precedence, `config/default.yaml` with all default values
- **Key decisions:** Config precedence: env var > YAML default > hardcoded fallback. YAML uses nested keys (e.g., `audio.input_sample_rate`). `PROJECT_ROOT` computed relative to `config.py`.
- **Deviations from spec:** None
- **Tests:** 6 tests in `tests/test_config.py` — env loading, yaml defaults, override precedence, hardcoded defaults, missing key validation, frozen immutability

#### Task 2 — Hardware Abstraction Layer
- **Status:** Complete
- **Files:** `src/hardware/interfaces.py`, `src/hardware/stubs.py`, `tests/fixtures/test_image.jpg`
- **What was built:** 4 ABCs (`AudioInput`, `AudioOutput`, `DisplayOutput`, `CameraInput`) with full docstrings. 4 stub implementations: `StubAudioInput` (reads WAV, loops, generates silence), `StubAudioOutput` (records to memory/WAV file), `StubDisplayOutput` (terminal print, stores last text/status), `StubCameraInput` (reads JPEG file or returns placeholder).
- **Key decisions:** StubAudioInput loops at end of file for continuous streaming tests. StubAudioOutput exposes `get_recorded_data()` for test assertions. StubCameraInput returns minimal JPEG SOI+EOI bytes as fallback.
- **Deviations from spec:** None
- **Tests:** 20 tests in `tests/test_hardware.py` — interface compliance, open/close lifecycle, chunk read/write, error on closed stream, WAV file output, silence generation, JPEG capture

#### Task 3 — Personality Configuration
- **Status:** Complete
- **Files:** `src/personality/voices.py`, `src/personality/manager.py`, `config/personalities/{friendly,professional,energetic,calm}.json`
- **What was built:** `VoiceInfo` frozen dataclass, `VOICE_CATALOG` with all 30 Gemini voices, `get_voice()` (case-insensitive), `list_voices()`. `PersonalityConfig` frozen dataclass, `PersonalityManager` class (loads from directory, validates against voice catalog, case-insensitive lookup). 4 pre-defined personality JSON files.
- **Key decisions:** Personality lookup uses filename stem (lowercase). Invalid JSON files are skipped with a warning rather than crashing. VAD sensitivity validated against {"LOW", "MEDIUM", "HIGH"} set.
- **Deviations from spec:** None
- **Tests:** 25 tests in `tests/test_personality.py` — voice catalog completeness, case-insensitive lookup, validation (missing fields, unknown voice, invalid VAD), manager loading, real personality files, frozen immutability

### Phase 2: Core Voice Pipeline

#### Task 4 — Gemini Live API Session Manager
- **Status:** Complete
- **Files:** `src/gemini/session.py`
- **What was built:** `GeminiSessionConfig` dataclass, `ServerMessage` dataclass (normalized message type), `GeminiSession` class wrapping `google-genai` SDK Live API. Session lifecycle: `connect()` opens WebSocket with full config (voice, system prompt, VAD, transcription, context compression), `send_audio()` streams PCM chunks, `receive()` async iterator yielding normalized `ServerMessage`s, `send_tool_response()` sends function call results, `close()` graceful shutdown. Message parser handles: setup_complete, audio, transcription, input_transcription, tool_call, turn_complete, interrupted, tool_call_cancellation, go_away, error.
- **Key decisions:** VAD sensitivity mapped to SDK enums (LOW/MEDIUM/HIGH → start/end sensitivity pairs). Tool call names stored internally so `send_tool_response()` only needs `call_id` + `result` (matching spec). Errors in `receive()` yield an error ServerMessage and set `is_connected=False`. Context window compression enabled by default.
- **Deviations from spec:** Added message types beyond spec minimum (input_transcription, interrupted, tool_call_cancellation, go_away, setup_complete) — downstream consumers can ignore unneeded types.
- **Tests:** 26 tests in `tests/test_session.py` — config creation, ServerMessage defaults, connect/close lifecycle, send_audio (connected + not connected), tool response with name mapping, receive for all message types (setup_complete, audio, transcription, input_transcription, turn_complete, interrupted, tool_call, go_away, error), parse_message (empty, multiple parts, name mapping, cancellation)

#### Task 5 — Audio Capture Pipeline
- **Status:** Complete
- **Files:** `src/audio/capture.py`
- **What was built:** `AudioCaptureStream` class. Reads PCM chunks from `AudioInput` in an async loop and sends them to `GeminiSession.send_audio()`. Uses `asyncio.create_task()` for concurrent capture alongside the receive loop. `run_in_executor()` wraps the blocking `read_chunk()` call. Does not reopen AudioInput if already open (compatible with wake word → capture handoff).
- **Key decisions:** Capture loop uses `run_in_executor` for blocking audio reads. Skips sending if session is disconnected (prevents errors). Does not reopen already-open audio streams (supports shared AudioInput with wake word detector). `start()` is idempotent.
- **Deviations from spec:** None
- **Tests:** 8 tests in `tests/test_capture.py` — start/stop lifecycle, sends audio chunks of correct size, skips when disconnected, silence input, reuse of open stream, idempotent start, stop when not started

#### Task 6 — Audio Playback Pipeline
- **Status:** Complete
- **Files:** `src/audio/playback.py`
- **What was built:** `AudioPlaybackStream` class. Buffers PCM audio chunks in an `asyncio.Queue`, starts a background drain task on first chunk. Drain loop: Phase 1 buffers `buffer_chunks` chunks, Phase 2 plays them, Phase 3 continues draining as new chunks arrive. `flush()` signals end of audio stream and waits for drain to complete. `stop()` immediately cancels playback and clears queue. `play_file()` plays local WAV files for cached error phrases.
- **Key decisions:** Uses `asyncio.Queue` with None sentinel for end-of-stream. Initial buffering (default 3 chunks) prevents stuttering. Drain loop exits on timeout (2s with no chunks) for automatic cleanup. `play_file()` writes in ~100ms chunks through `run_in_executor`. `stop()` cancels drain task and calls `AudioOutput.stop()` for immediate interruption.
- **Deviations from spec:** Added `flush()` method (not in spec) — useful for signaling end of a turn's audio and waiting for playback to finish.
- **Tests:** 11 tests in `tests/test_playback.py` — play_chunk opens stream, buffered playback with flush, single chunk, stop interruption, queue clearing, play_file from WAV, nonexistent file handling, stop flag behavior, multiple turns, flush when not playing, is_playing state after drain

#### Task 7 — Wake Word Detection
- **Status:** Complete
- **Files:** `src/wake_word/detector.py`
- **What was built:** `WakeWordDetector` class wrapping OpenWakeWord. Async detection loop reads 1024-byte PCM chunks from `AudioInput`, accumulates to 2560 bytes (1280 int16 samples = one OWW frame), runs `model.predict()` in executor, fires async callback when score >= sensitivity. `pause()`/`resume()` for use during Gemini conversations. Both call `model.reset()` to clear stale audio features.
- **Key decisions:** Default wake word is `hey_jarvis` (built-in model) since "hey robot" requires custom training. Audio chunks accumulated to 2560 bytes before calling OWW `predict()` (OWW needs 1280 samples minimum). Detection resets model after firing to prevent rapid re-triggers. `run_in_executor` used for both `read_chunk()` and `predict()`. Does not reopen AudioInput if already open.
- **Deviations from spec:** Default wake_word changed from "hey robot" to "hey_jarvis" — no pretrained model exists for "hey robot" and custom training is deferred. On-device wake word training noted as future enhancement.
- **Tests:** 13 tests in `tests/test_wake_word.py` — start/stop lifecycle, callback fires on detection (score >= threshold), no callback below threshold, pause prevents detection, resume re-enables detection, model reset on pause/resume, silence input, stop closes audio, idempotent start, default sensitivity, reuse of open stream, audio format verification (int16 arrays of 1280 samples)

### Phase 3: Robot Assembly

#### Task 8 — Robot Main Controller
- **Status:** Complete
- **Files:** `src/core/state_machine.py`, `src/core/controller.py`
- **What was built:** `RobotState` enum (IDLE, CONNECTING, CONVERSATION, SHUTTING_DOWN). `RobotController` class orchestrating the full voice interaction loop: wake word detection triggers Gemini session, bidirectional audio streaming during conversation, silence timeout returns to idle, graceful shutdown. State handlers: `_run_idle()` starts wake word detector and waits for detection or stop, `_run_connecting()` loads personality and opens Gemini session, `_run_conversation()` runs concurrent audio capture, receive loop, and timeout monitor. Handles all ServerMessage types: audio→playback, transcription→display, input_transcription→display, turn_complete→flush+timer reset, interrupted→stop playback, tool_call→error response (MCP pending Task 9), error/go_away→end conversation.
- **Key decisions:** Wake word detector stopped (not paused) during conversation to release AudioInput for capture stream — both can't read concurrently. Detector restarted when returning to IDLE. Silence timeout via separate `_timeout_monitor` task (1s polling) since receive loop blocks on WebSocket. `asyncio.wait(FIRST_COMPLETED)` used to race receive loop vs timeout. `_wait_for_event_or_stop` helper enables clean shutdown during IDLE wait. Tool calls send back error response with message "Tool execution not yet available." until MCP is implemented in Task 9. Personality's `conversation_timeout_seconds` overrides default timeout.
- **Deviations from spec:** None. All spec requirements implemented.
- **Tests:** 26 tests in `tests/test_controller.py` — state enum, init, IDLE state (wake word transition, stop during idle, display status), CONNECTING (success, failure, personality config, fallback to default, display), CONVERSATION (audio playback, transcription display, input transcription, error/go_away end, tool call response, silence timeout, session cleanup, display), full lifecycle (complete cycle, immediate stop, retry after failure), shutdown (cleanup, stop flags)

### Phase 4: Extensibility

#### Task 9 — MCP Tool Server
- **Status:** Complete
- **Files:** `src/tools/server.py`
- **What was built:** `ToolParam` (frozen dataclass for parameter definitions), `ToolDefinition` (dataclass for tool metadata + handler), `ToolServer` class with: `register_tool()` for single tools, `register_builtin_tools()` for hardware-bound display/camera tools, `discover_user_tools()` for auto-loading from a directory, `get_tool_declarations()` returning Gemini-compatible dict-format function declarations, `execute_tool()` supporting both sync and async handlers with error handling. User tools loaded from Python files exporting a `TOOLS` list.
- **Key decisions:** Tool declarations returned as raw dicts (not google.genai types) — the google-genai SDK accepts dict-format tools, keeping ToolServer free of external dependencies. Async handler support via `inspect.isawaitable()`. User tool files must export a `TOOLS` list of `ToolDefinition` objects. Files starting with `_` are skipped. Broken modules are logged and skipped.
- **Deviations from spec:** Spec suggested using FastMCP server directly, but we use a simpler custom ToolServer that bridges to Gemini's function calling format. FastMCP remains in requirements.txt for future external MCP client support.
- **Tests:** 19 tests in `tests/test_tools.py` — ToolParam/ToolDefinition basics, registration, execution (sync, async, unknown, error, non-dict result), declarations (empty, with params, without params, multiple tools, optional params), builtin registration, user tool discovery (missing dir, empty, valid, underscore skip, broken modules, non-tool items)

#### Task 10 — Display Module
- **Status:** Complete
- **Files:** `src/tools/display.py`
- **What was built:** `create_display_tools(display)` factory that creates three `ToolDefinition` objects bound to a `DisplayOutput` instance: `display_text(text)` shows text and returns confirmation, `display_status(status)` shows a status indicator, `clear_display()` clears the screen. All return `{"status": "ok", ...}` dicts.
- **Key decisions:** Tools are created via factory function bound to a specific display instance (closure pattern). Each tool returns a confirmation dict for Gemini to understand the action was performed.
- **Deviations from spec:** None
- **Tests:** 6 tests in `tests/test_tools.py` — creates correct number of tools, display_text/status/clear handlers work, parameter definitions correct, end-to-end via server

#### Task 11 — Camera Module
- **Status:** Complete
- **Files:** `src/tools/camera.py`
- **What was built:** `create_camera_tools(camera)` factory that creates one `ToolDefinition` bound to a `CameraInput` instance: `capture_camera_frame()` captures a frame, returns base64-encoded JPEG with metadata (mime_type, size_bytes).
- **Key decisions:** Camera frames base64-encoded for Gemini consumption. Returns size_bytes for the model to understand image size. No parameters needed (single-frame capture).
- **Deviations from spec:** None
- **Tests:** 6 tests in `tests/test_tools.py` — creates correct tool, returns base64, works with test image file, stub JPEG, no params, end-to-end via server

### Phase 5: Optional

#### Task 12 — n8n Integration
- **Status:** Not Started
- **Files:** MCP tool in `src/tools/`, existing `server/docker-compose.yml`
- **What was built:** —
- **Key decisions:** —
- **Deviations from spec:** —
- **Tests:** —

### Phase 6: Hardening

#### Task 13 — Error Handling & Reconnection
- **Status:** Not Started
- **Files:** Updates to `src/gemini/session.py`, `src/core/controller.py`, `scripts/generate_phrases.py`
- **What was built:** —
- **Key decisions:** —
- **Deviations from spec:** —
- **Tests:** —

#### Task 14 — Logging & Monitoring
- **Status:** Not Started
- **Files:** `src/core/logging.py`
- **What was built:** —
- **Key decisions:** —
- **Deviations from spec:** —
- **Tests:** —

#### Task 15 — CLI Test Client & E2E Tests
- **Status:** Not Started
- **Files:** `scripts/test_client.py`, `tests/test_e2e.py`
- **What was built:** —
- **Key decisions:** —
- **Deviations from spec:** —
- **Tests:** —

---

## Open Questions & Decisions

| # | Question | Status | Decision | Date |
|---|----------|--------|----------|------|
| 1 | What specific hardware for the robot? | Open | — | — |
| 2 | OpenWakeWord custom model training approach? | Open | User wants on-device training option; deferred post-Phase 6 | 2026-02-09 |
| 3 | Python vs Go for implementation language? | Decided | Python (Session 4) | 2026-02-08 |
| 4 | Default wake word model? | Open | Using "hey_jarvis" for dev; need to train custom "hey robot" model | 2026-02-09 |

---

## Interface Change Log

Track any changes to the interface contracts defined in `docs/robot_voice_pipeline_tasks.md`.

| Date | Interface | Change | Affected Tasks | Reason |
|------|-----------|--------|----------------|--------|
| 2026-02-09 | `ServerMessage.type` | Added types: `input_transcription`, `interrupted`, `setup_complete`, `go_away`, `tool_call_cancellation` beyond spec minimum | Task 8 | Gemini SDK provides these events; downstream can ignore unneeded types |
| 2026-02-09 | `AudioPlaybackStream` | Added `flush()` method | Task 8 | Needed to signal end-of-turn audio and wait for drain to complete |
| 2026-02-09 | `WakeWordDetector.__init__` | Default `wake_word` changed from `"hey robot"` to `"hey_jarvis"` | Task 8 | No pretrained model for "hey robot"; custom training deferred |
| 2026-02-10 | `RobotController` | Added ToolServer integration — creates ToolServer, registers builtin tools, passes declarations to Gemini config, executes tool calls | Task 9, 10, 11 | MCP tool system now active; tool calls execute real tools instead of returning error |
| 2026-02-10 | `GeminiSessionConfig.tools` | Now receives dict-format tool declarations from ToolServer | Task 9 | Dict format accepted by google-genai SDK, keeps ToolServer free of google deps |

---

## Session Log

### Session 1 — 2026-02-07
- **Tasks worked on:** Project setup
- **What was accomplished:**
  - Reviewed design doc and task breakdown
  - Created `CLAUDE.md` (project rules and context for Claude Code)
  - Created `docs/PROGRESS.md` (this file)
- **Decisions made:** Tasks in PROGRESS.md grouped by implementation phase
- **Issues encountered:** None
- **Next steps:** Begin Task 1 (Hardware Abstraction Layer) and Task 2 (Project Scaffold)

### Session 2 — 2026-02-07
- **Tasks worked on:** Task 4 (n8n Server Setup), Task 6 (Voice Pipeline Workflow) — old architecture
- **What was accomplished:**
  - Created `server/docker-compose.yml` with n8n + PostgreSQL 16
  - Created `scripts/setup_n8n.sh` setup script with health checks
  - Created `.env.example` with environment variables
  - Created `server/workflows/voice-pipeline.json` — starter workflow
  - Created `server/personality-cache/.gitkeep`
- **Decisions made:** Started server tasks early per user request
- **Issues encountered:** None
- **Next steps:** Test docker-compose and workflow

### Session 3 — 2026-02-08
- **Tasks worked on:** Architecture redesign
- **What was accomplished:**
  - **Major architecture change:** Replaced n8n-orchestrated voice pipeline with direct Gemini Live API (native audio-to-audio)
  - Rewrote `docs/robot_voice_pipeline_design.md` (v2.0 → v3.0)
  - Rewrote `docs/robot_voice_pipeline_tasks.md` — new 15-task breakdown in 6 phases
  - Reset `docs/PROGRESS.md` — all tasks reset to Not Started
  - Updated `CLAUDE.md` — new architectural rules for Gemini Live API
  - Updated `.env.example` — new environment variables
- **Decisions made:**
  - Gemini 2.5 Flash Live API replaces n8n + Gemini text + Google TTS
  - Robot is now a "smart client" connecting directly via WebSocket
  - Multi-turn conversation (wake word starts session, natural back-and-forth)
  - MCP tools for extensibility (display, camera, user tools, n8n triggers)
  - OpenWakeWord (Apache 2.0) chosen for wake word detection
  - n8n kept as optional for automation workflows, not part of voice pipeline
  - Source code moves from `robot/` to `src/` with new module structure
- **Superseded work:**
  - Old Task 4 (n8n Docker setup) → kept as-is for optional Task 12
  - Old Task 6 (n8n voice workflow) → superseded, kept as reference in `server/workflows/`
- **Issues encountered:** None
- **Next steps:** Begin Task 1 (Project Scaffold & Config System)

### Session 4 — 2026-02-08
- **Tasks worked on:** Task 1, Task 2, Task 3 (full Phase 1)
- **What was accomplished:**
  - Created full directory structure with `src/` and 9 subpackages, all `__init__.py` files
  - Built `src/core/config.py` — `Settings` frozen dataclass + `load_settings()` (env > yaml > defaults)
  - Created `config/default.yaml` with all default config values
  - Created `requirements.txt` with all Python dependencies
  - Built `src/hardware/interfaces.py` — 4 ABCs (AudioInput, AudioOutput, DisplayOutput, CameraInput)
  - Built `src/hardware/stubs.py` — 4 desktop stub implementations
  - Built `src/personality/voices.py` — 30-voice catalog with VoiceInfo dataclass
  - Built `src/personality/manager.py` — PersonalityConfig + PersonalityManager
  - Created 4 personality JSON files (friendly, professional, energetic, calm)
  - Created test fixtures: `tests/fixtures/test_image.jpg`
  - Wrote 51 tests across 3 test files — all passing
- **Decisions made:**
  - Config uses 3-tier precedence: env var > YAML > hardcoded default
  - YAML keys are nested (e.g., `audio.input_sample_rate`)
  - Stub audio input loops at end of WAV data for continuous streaming
  - PersonalityManager skips invalid files with warning rather than crashing
  - Python chosen for implementation (staying with spec, despite Go consideration)
- **Issues encountered:** pip not available — bootstrapped via get-pip.py
- **Next steps:** Begin Phase 2 (Task 4 — Gemini Live API Session Manager)

### Session 5 — 2026-02-09
- **Tasks worked on:** Task 4, Task 5, Task 6, Task 7 (full Phase 2)
- **What was accomplished:**
  - Built `src/gemini/session.py` — Full Gemini Live API session manager wrapping `google-genai` SDK. Handles WebSocket connect, audio send/receive, tool call handling, graceful close. Normalizes all SDK message types into `ServerMessage` dataclass.
  - Built `src/audio/capture.py` — Async audio capture pipeline. Reads PCM chunks from AudioInput in executor, sends to GeminiSession. Runs as asyncio task.
  - Built `src/audio/playback.py` — Async audio playback pipeline with initial buffering (configurable chunks). Uses asyncio.Queue + drain task. Supports interruption via `stop()`, WAV file playback for cached phrases, and `flush()` for end-of-turn.
  - Built `src/wake_word/detector.py` — OpenWakeWord integration. Accumulates 1024-byte chunks to 2560-byte OWW frames, runs predictions in executor, fires async callback on detection. Supports pause/resume with model reset.
  - Created `pyproject.toml` — pytest-asyncio auto mode configuration
  - Installed dependencies: google-genai, openwakeword, numpy, pytest-asyncio
  - Wrote 59 new tests across 4 test files — all 110 tests passing (51 Phase 1 + 59 Phase 2)
- **Decisions made:**
  - VAD sensitivity mapped to SDK start/end sensitivity enum pairs (LOW→low/low, MEDIUM→high/low, HIGH→high/high)
  - Tool call names stored internally in session (call_id → name mapping) so `send_tool_response()` matches spec signature
  - Audio capture uses `run_in_executor` for blocking `read_chunk()` calls
  - Playback uses asyncio.Queue with None sentinel for end-of-stream signaling
  - Wake word detector accumulates to 2560 bytes (1280 samples) before calling OWW predict
  - Default wake word is `hey_jarvis` (pretrained model available); custom "hey robot" model training deferred
  - User wants on-device wake word training — noted for post-Phase 6 enhancement
- **Issues encountered:** None
- **Next steps:** Phase 3 — Task 8 (Robot Main Controller)

### Session 6 — 2026-02-10
- **Tasks worked on:** Task 8 (Phase 3 — Robot Assembly)
- **What was accomplished:**
  - Built `src/core/state_machine.py` — `RobotState` enum with 4 states and documented transitions
  - Built `src/core/controller.py` — `RobotController` class (~250 lines) orchestrating the full voice interaction loop as a state machine. Ties together WakeWordDetector, GeminiSession, AudioCaptureStream, AudioPlaybackStream, PersonalityManager, and optional display/camera
  - State flow: IDLE (wake word listening) → CONNECTING (Gemini session setup with personality config) → CONVERSATION (bidirectional audio, message handling, silence timeout) → back to IDLE
  - Handles all ServerMessage types including audio playback, transcription display, interruption handling, and tool call error responses
  - Wrote 26 tests in `tests/test_controller.py` covering all states, transitions, message handling, timeout, lifecycle, and shutdown
  - All 136 tests passing (110 Phase 1+2 + 26 Phase 3)
- **Decisions made:**
  - Wake word detector stopped (not paused) during conversation to prevent concurrent reads from shared AudioInput — restarted on return to IDLE
  - Silence timeout via separate asyncio task with 1s polling since receive loop blocks on WebSocket
  - asyncio.wait(FIRST_COMPLETED) to race receive loop vs timeout monitor
  - Tool calls send error response until MCP server is implemented in Task 9
  - Personality's conversation_timeout_seconds overrides global settings timeout
- **Issues encountered:** None
- **Next steps:** Phase 4 — Task 9 (MCP Tool Server)

### Session 7 — 2026-02-10
- **Tasks worked on:** Task 9, Task 10, Task 11 (full Phase 4)
- **What was accomplished:**
  - Built `src/tools/server.py` — ToolServer class managing tool registration, execution (sync + async), user tool discovery, and Gemini-compatible dict-format declarations. ToolParam and ToolDefinition dataclasses for tool metadata.
  - Built `src/tools/display.py` — Factory function creating 3 display tools (display_text, display_status, clear_display) bound to a DisplayOutput instance.
  - Built `src/tools/camera.py` — Factory function creating 1 camera tool (capture_camera_frame) returning base64-encoded JPEG.
  - Updated `src/core/controller.py` — Integrated ToolServer: creates on init, registers builtin tools based on available hardware, passes tool declarations to Gemini session config, executes tool calls via ToolServer (replacing the old error stub).
  - Updated `tests/test_controller.py` — Fixed tool_call test for new behavior, added test for registered tool execution via display.
  - Created `tests/test_tools.py` — 41 new tests covering server, display, and camera tools.
  - All 177 tests passing (136 previous + 41 new)
- **Decisions made:**
  - ToolServer returns dict-format declarations (not google.genai types) for SDK compatibility and testability
  - User tools discovered via `TOOLS` list convention in Python files
  - Tool handlers support both sync and async (via inspect.isawaitable)
  - Display tools use closure pattern to bind to hardware instance
  - Camera frames base64-encoded for Gemini multimodal consumption
  - Tool calls now reset the activity timer (prevents timeout during tool execution)
- **Issues encountered:** None
- **Next steps:** Phase 5 (Task 12 — n8n Integration, optional) or Phase 6 (Tasks 13-15 — Hardening)
