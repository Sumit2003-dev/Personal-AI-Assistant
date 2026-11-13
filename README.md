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

## 6. How to Launch and Test SAM

### Run the Automated Test Suite:
```powershell
python -m unittest sam.tests.test_suite -v
```

### Launch the Desktop Interface:
```powershell
python -m sam.app.main --mode desktop --port 8765
```
Open your browser or web app window to: `http://127.0.0.1:8765`

### Query System Status via CLI:
```powershell
python -m sam.app.main --mode status
```

### Execute a Preset Workflow directly:
```powershell
python -m sam.app.main --workflow A    # Coding
python -m sam.app.main --workflow B    # Video Edit (1080p vertical)
python -m sam.app.main --workflow C    # Browser Research
python -m sam.app.main --workflow D    # Hardware Telemetry
python -m sam.app.main --workflow E    # PDF Intelligence
```

