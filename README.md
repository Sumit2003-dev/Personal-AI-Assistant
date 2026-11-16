# PROJECT SAM – AUTONOMOUS AI COMPUTER OPERATOR

> **Advanced Autonomous Computer-Use Operator for Windows 11**  
> Tailored & Optimized for HP OMEN 16 • NVIDIA GeForce RTX 4050 Laptop GPU (6GB VRAM) • 16GB RAM • Local-First Intelligence (Ollama / Qwen3 4B)

---

## 1. System Overview

**SAM** is an autonomous AI computer operator designed to control real Windows applications, plan multi-step operations, observe screen and system state, recover from failures, and verify outcomes before reporting success.

SAM is **not a chatbot**. It is an end-to-end execution system that drives the Windows desktop via native Win32 APIs, computer-use automation, application registries, and multimodal vision loops.

```
                      +---------------------------------------+
                      |       USER INTENT (Voice / Text)      |
                      +---------------------------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |         TASK PLANNER & GOAL           |
                      |           DECOMPOSITION               |
                      +---------------------------------------+
                                          |
             +----------------------------+----------------------------+
             |                                                         |
             v                                                         v
+--------------------------+                             +--------------------------+
|    SECURITY GATEKEEPER   |                             |   LOCAL MODEL PROVIDER   |
| Low / Medium / High Risk |                             |    Ollama (qwen3:4b)     |
|  Global Emergency Stop   |                             | Deterministic Fallback   |
+--------------------------+                             +--------------------------+
             |                                                         |
             +----------------------------+----------------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |       OBSERVE-PLAN-ACT-VERIFY         |
                      |            EXECUTION LOOP             |
                      +---------------------------------------+
                                          |
             +----------------------------+----------------------------+
             |                            |                            |
             v                            v                            v
  [ COMPUTER USE & WIN32 ]      [ SPECIALIZED AGENTS ]      [ HARDWARE TELEMETRY ]
  - Mouse & Keyboard Input      - Autonomous Coding         - NVIDIA RTX 4050 VRAM
  - Screen Capture & Diff       - Video Editing (1080p)     - CPU / RAM / Disk C & D
  - Window Targeter             - Browser & Documents       - Thermal Diagnostics
                                          |
                                          v
                      +---------------------------------------+
                      |        POST-ACTION VERIFICATION       |
                      |  Artifact Validation & Outcome Check  |
                      +---------------------------------------+
```

---

## 2. Hardware Environment Profile (HP OMEN 16)

SAM is calibrated specifically for the host hardware:

| Component | Host Specification | SAM Optimization Strategy |
| :--- | :--- | :--- |
| **Device** | HP OMEN 16 | Dedicated cooling awareness & thermal monitoring |
| **OS** | Windows 11 Home/Pro 64-bit | Native Win32 / SendInput / Display DPI Scaling |
| **GPU** | NVIDIA GeForce RTX 4050 Laptop GPU | 6141 MiB Total VRAM (~5.2 GB Free allocated for Qwen3 4B) |
| **RAM** | 16 GB DDR5 | Memory safety threshold at 85% utilization |
| **Storage** | 512 GB SSD (C: & D: partitions) | C: (13.3 GB free), D: (263.7 GB free) - Auto workspace redirect |
| **Inference Runtime** | Ollama | Single model concurrency to prevent VRAM exhaustion |

---

## 3. Modular Architecture

```
sam/
  app/              # Main CLI and desktop bootstrap entry point
  desktop/          # PySide6 & Futuristic Cyber Web-Desktop UI (10 sections)
    static/         # CSS neon styling, audio waveform canvas, JS controller
    templates/      # HTML5 Cyber Desktop Interface
  agent/            # Core data contracts (Task, TaskStep, RiskLevel, Observation)
  planner/          # Goal interpreter & step decomposition engine
  executor/         # Observe-Plan-Act-Verify execution loop & retry manager
  computer_use/     # Native Win32 mouse, keyboard, window, & session mutex
  vision/           # Screen grabber, dHash perceptual diff, OpenCV template matcher
  tools/            # Central tool registry with input/output validation contracts
  integrations/     # Application registry (VS Code, Edge, Chrome, Word, Excel, DaVinci)
  coding/           # Autonomous coding agent (workspace inspector, script runner)
  video/            # Video pipeline (FFmpeg/OpenCV, 9:16 vertical 1080p, subtitles)
  browser/          # Browser autonomy (Edge/Chrome launcher, content extractor)
  voice/            # Voice interface (wake phrase "Hey SAM", push-to-talk, VAD)
  memory/           # SQLite long-term storage (preferences, workflows, task history)
  documents/        # Document engine (PDF, DOCX, XLSX, CSV parsing & reports)
  security/         # Risk gatekeeper, command sanitizer, global emergency stop
  monitoring/       # Real-time hardware telemetry (CPU, RAM, GPU, Disks)
  config/           # Hardware limits, paths, Ollama settings
  tests/            # Automated test suite (15 verification tests)
  logs/             # Append-only audit log (audit.jsonl)
  data/             # Workspaces, exports, screenshots, and SQLite database
```

---

## 4. Acceptance Criteria Workflows (Demonstrated & Verified)

All 5 core workflows defined in Section 18 are implemented and pass verification:

- **Workflow A (Coding Agent):**  
  `"Open VS Code, create a Python project, write a script, run it and fix errors."`  
  *Execution:* Initializes isolated workspace, creates source file, executes subprocess, captures stdout, and asserts 0 exit code.

- **Workflow B (Video Editing Agent):**  
  `"Open a selected video, create a vertical 1080p edit, add generated subtitles and export the finished video."`  
  *Execution:* Inspects source media, configures 9:16 vertical pipeline, generates synchronized SRT subtitles, renders 1080x1920 video with subtitle overlays, and validates decodability. Original footage is strictly preserved.

- **Workflow C (Browser Autonomy):**  
  `"Open a browser, research a topic, collect information and prepare a report."`  
  *Execution:* Launches Microsoft Edge or Chrome, extracts clean semantic text, and compiles a structured markdown research report.

- **Workflow D (Hardware Telemetry):**  
  `"Check my laptop's CPU, RAM, GPU and disk usage and explain any issues."`  
  *Execution:* Queries real-time counters from `nvidia-smi` and `psutil`. Automatically diagnoses that Drive C:\ is 93% full while Drive D:\ has 263+ GB available.

- **Workflow E (Document Intelligence):**  
  `"Open my selected PDF, summarize it and answer questions about its contents."`  
  *Execution:* Reads PDF structure via `pypdf`, parses metadata and text blocks, extracts key takeaways, and compiles an executive summary.

---

## 5. Security & Risk Management

SAM implements a strict three-tier risk model:

| Risk Level | Allowed Operations | Guardrail |
| :--- | :--- | :--- |
| **LOW** | System telemetry, reading files, searching approved folders | Executed automatically with audit logging |
| **MEDIUM** | Writing workspace code, running test scripts, rendering video | Allowed in approved workspaces; logged |
| **HIGH** | File deletion, overwriting originals, external publishing, admin actions | Requires **explicit user confirmation modal** |

- **Global Emergency STOP:** Immediately halts all running automation and terminates active session locks. Can be triggered from UI or API.
- **Audit Log:** Complete history saved in `sam/logs/audit.jsonl`.

---

## 6. Phase 6 Agent Integration & Architecture

Phase 6 connects the desktop interface and autonomous planner with fully integrated, production-grade specialized agents:

1. **AI Orchestration & Long-Term Memory Injection**
   - Natural language goals automatically query `memory_store` for relevant personal facts, preferences, and recent chat history.
   - Context is injected directly into local LLM (`qwen2.5:3b` / `qwen3:4b`) prompts for structured JSON plan generation.
   - Tasks execute via an Observe-Plan-Act-Verify cycle with progress callbacks and audit logging.

2. **Computer-Use Agent & Session Mutex**
   - Integrates real Windows desktop screen capture (`screen_observer`), active window focus tracking (`window_manager`), and mouse/keyboard controllers.
   - Enforces a thread-safe `session_manager` mutex ensuring only one desktop automation holds control at a time.
   - Compares pre- and post-action visual perceptual hashes (`dHash`) to verify visual state changes on GUI interactions.

3. **Coding Agent with Checkpoints & Diagnostics**
   - Safely creates and edits files in isolated workspaces with path traversal prevention.
   - **Automatic Checkpointing:** Overwriting an existing file automatically creates a `.bak` backup copy.
   - **Rollback Tool:** Instantly restores original source files from `.bak` checkpoints (`coding_rollback_file`).
   - **Traceback Diagnostics:** Parses Python runtime tracebacks to extract failing line numbers, exception types, and stack frame depths.
   - **Test Runner:** Discovers and runs automated unit tests (`coding_run_tests`).

4. **Browser Autonomy Engine & Submission Security**
   - Discovers installed browsers (Edge, Chrome) via Windows Application Registry.
   - Structured search (`browser_search`) extracts titles, snippets, and clean target URLs.
   - Link extraction (`browser_extract_links`) parses navigable anchors on web pages.
   - **External Submission Gating:** Form submissions and HTTP POST requests (`browser_submit_form`) are marked **HIGH RISK** and require explicit user confirmation through the security gatekeeper before dispatch.

5. **Document Intelligence Engine**
   - Parses PDF (`pypdf`), DOCX (`docx`), and spreadsheets/tabular data (`pandas` XLSX, CSV).
   - Strict read-only mode (`"rb"`, `"r"`) guarantees original source files are never altered or overwritten.
   - Exports executive analysis reports to dedicated report directories (`document_export_analysis`).

6. **Video Editing Pipeline (Non-Destructive)**
   - Renders 9:16 vertical 1080p clips (`1080x1920`) with OpenCV and FFmpeg backends.
   - Generates synchronized subtitles and burned-in captions.
   - Trims source clips (`video_trim_clip`) while strictly preserving original footage in dedicated export folders (`sam/data/video_exports`).

7. **Security Gatekeeper & Emergency Stop**
   - Centralized risk gating across all agents (LOW, MEDIUM, HIGH).
   - Global emergency stop halts active tasks immediately and releases all computer-use session locks.
   - Task lifecycle controls: Pause, Resume, Stop/Cancel, Approve, and Reject.

---

## 7. Phase 6.1 Reliability, Safety & Integration Hardening

Phase 6.1 resolves critical reliability, hardware safety, and security edge cases across all subsystems:

1. **Voice Reliability & Microphone Safety Guardrails**
   - **Persistent Device Memory:** Hardens `boAt Airdopes 131` as user-preferred device across system reboots and Bluetooth disconnects; prevents silent permanent fallback to Intel Smart Sound.
   - **Pre-Transcription Quality Screening:** Computes RMS energy, peak amplitude, clipping ratio, and silence ratio before touching Whisper. Recordings below `rms < 0.008` or `peak < 0.025` are rejected upfront with explanatory diagnostic reasons.
   - **Whisper Hallucination Suppression:** Rejects hallucinated single-word artifacts (`"You"`, `"Thank you"`, `"MBC"`) generated from background mic hiss, and enforces confidence thresholds on `no_speech_prob <= 0.45` and `avg_logprob >= -1.1`.
   - **Human-in-the-Loop Gating:** Structured JSON results (`is_valid`, `rejection_reason`, `audio_metrics`, `editable_transcript`) require explicit transcript preview and confirmation before planner submission.

2. **Desktop Observation & Outcome Verification**
   - **Explicit Failure Representation:** Observations distinguish real screen grabs from failed observations (`is_placeholder=True`, `success=False`, `error`).
   - **Action-Specific Verification:** Confirms file existence and non-zero byte size on disk for write/export operations; checks non-zero script exit codes; verifies target window title matches on window focus.
   - **Emergency Stop Lock Clearance:** Triggering emergency stop forcibly terminates computer-use session locks (`session_manager.force_release()`) and blocks subsequent acquisition until explicitly reset.

3. **Browser Automation Audit & Playwright Integration**
   - Distinguishes interactive Playwright headless automation from HTTP/HTML extraction modes.
   - Enforces HIGH RISK security gatekeeper approval on consequential actions (purchases, payments, order placements, account settings changes, deletions, and external form submissions).

4. **Workspace Containment & Security**
   - Blocks path traversal (`../`), drive letter escapes (`C:\Windows`), illegal path characters (`<>:"|?*`), Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`), and symlink escapes.
   - Confines file writing, reading, rollback, script execution, and unit testing strictly to approved workspace directories.

5. **Task Lifecycle Finite State Machine (FSM)**
   - Strict transition rules prevent illegal lifecycle transitions (e.g., terminal states `COMPLETED/STOPPED/FAILED` cannot transition to `RUNNING`).
   - Emergency stop and task cancellation halt execution immediately and block subsequent retry loops.

---

## 8. How to Launch and Test SAM

### Run the Full Verification Suite (73 Automated Tests):
```powershell
# 1. Run Phase 6.1 Reliability & Safety Suite (24 tests):
python -m unittest sam.tests.test_phase6_1_hardening -v

# 2. Run Phase 6 Agent Integrations Suite (13 tests):
python -m unittest sam.tests.test_agent_integrations -v

# 3. Run Desktop Web API Suite (11 tests):
python -m unittest sam.tests.test_desktop_api -v

# 4. Run Core System & Acceptance Suite (25 tests):
python -m unittest sam.tests.test_suite -v
```

### Launch the Interactive Desktop Workstation:
```powershell
python -m sam.app.main --mode desktop --port 8765
```
Open your browser to: `http://127.0.0.1:8765`

### Query System Status via CLI:
```powershell
python -m sam.app.main --mode status
```

### Execute a Preset Workflow directly:
```powershell
python -m sam.app.main --workflow A    # Coding Agent (Create, Run, Verify)
python -m sam.app.main --workflow B    # Video Pipeline (1080p vertical edit)
python -m sam.app.main --workflow C    # Browser Autonomy (Search & Extract)
python -m sam.app.main --workflow D    # Hardware Telemetry (RTX 4050 / CPU / RAM / Disk)
python -m sam.app.main --workflow E    # Document Intelligence (PDF Summarization)
```

