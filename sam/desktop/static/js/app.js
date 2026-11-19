// =========================================================
// SAM - Desktop Client Controller (v2.0)
// Complete Interactive AI Workstation Controller
// =========================================================

let currentTaskId = null;
let isEmergencyStopped = false;
let screenRefreshTimer = null;
let autoRefreshScreen = true;

// ---------------------------------------------------------
// Tab Navigation
// ---------------------------------------------------------
document.querySelectorAll(".nav-item").forEach(item => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
    item.classList.add("active");
    const target = item.getAttribute("data-tab");
    const pane = document.getElementById(target);
    if (pane) {
      pane.classList.add("active");
      onTabActivated(target);
    }
  });
});

function onTabActivated(tabId) {
  if (tabId === "paneComputer") {
    refreshLiveScreen();
    fetchActiveWindow();
  } else if (tabId === "paneTasks") {
    loadTaskHistory();
  } else if (tabId === "paneVoice") {
    refreshAudioDevices();
  } else if (tabId === "paneCoding") {
    loadCodingWorkspaces();
  } else if (tabId === "paneVideo") {
    loadVideoExports();
  } else if (tabId === "paneFiles") {
    loadDocFiles();
  } else if (tabId === "paneMemory") {
    loadAllMemories();
  } else if (tabId === "paneSettings") {
    loadSettingsAndAudit();
  }
}

// ---------------------------------------------------------
// Telemetry Polling (every 2 seconds)
// ---------------------------------------------------------
async function updateTelemetry() {
  try {
    const res = await fetch("/api/telemetry");
    if (res.ok) {
      const data = await res.json();
      const cpu = data.cpu ? data.cpu.cpu_percent_overall : 0;
      const ram = data.ram ? data.ram.used_percent : 0;
      const gpu = data.gpu;

      document.getElementById("telemetryCpu").textContent = `CPU: ${cpu}%`;
      document.getElementById("telemetryRam").textContent = `RAM: ${ram}%`;

      if (gpu && gpu.available) {
        document.getElementById("telemetryGpu").textContent = `RTX 4050: ${gpu.vram_used_mb}MB (${gpu.temperature_c}°C)`;
      } else {
        document.getElementById("telemetryGpu").textContent = "RTX 4050: Standby";
      }

      const dot = document.getElementById("dotStatus");
      if (dot) {
        dot.className = isEmergencyStopped ? "indicator-dot danger" : (cpu > 85 ? "indicator-dot warning" : "indicator-dot");
      }
    }
  } catch (e) {
    console.warn("Telemetry fetch warning:", e);
  }
}
setInterval(updateTelemetry, 2000);
updateTelemetry();

// ---------------------------------------------------------
// AI Chat & Multi-line Text Input
// ---------------------------------------------------------
const chatInput = document.getElementById("chatInput");
if (chatInput) {
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendChat();
    }
  });

  // Auto-resize textarea
  chatInput.addEventListener("input", function() {
    this.style.height = "auto";
    this.style.height = Math.min(this.scrollHeight, 120) + "px";
  });
}

async function handleSendChat() {
  const text = chatInput.value.trim();
  if (!text) return;

  appendChatBubble("user", text);
  chatInput.value = "";
  chatInput.style.height = "auto";

  // Temporary thinking indicator
  const thinkingId = appendChatBubble("sam", "<em>Planning autonomous task with local LLM...</em>");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text })
    });
    const data = await res.json();

    const thinkingBubble = document.getElementById(thinkingId);
    if (data.success) {
      currentTaskId = data.task_id;
      const stepsSummary = (data.steps || []).map((s, idx) => `<div>[${idx + 1}] <strong>${escapeHtml(s.title)}</strong> (tool: <code>${escapeHtml(s.tool_name)}</code>)</div>`).join("");
      
      const responseHtml = `
        <div>Task accepted: <strong>${data.task_id}</strong></div>
        <div style="font-size: 11.5px; color: var(--accent-cyan); margin: 4px 0;">Planned by: ${data.planned_by} • ${data.steps_count} verified operations</div>
        <div style="font-family: var(--font-mono); font-size: 11px; margin-top: 8px; border-top: 1px solid var(--border-subtle); padding-top: 6px;">
          ${stepsSummary}
        </div>
      `;
      if (thinkingBubble) thinkingBubble.querySelector(".msg-content").innerHTML = responseHtml;
      pollTaskStatus(data.task_id);
    } else {
      if (thinkingBubble) thinkingBubble.querySelector(".msg-content").innerHTML = `<span style="color: var(--accent-rose);">Error: ${data.error || "Failed to create task."}</span>`;
    }
  } catch (e) {
    const thinkingBubble = document.getElementById(thinkingId);
    if (thinkingBubble) thinkingBubble.querySelector(".msg-content").innerHTML = `<span style="color: var(--accent-rose);">Execution connection error: ${e.message}</span>`;
  }
}

function appendChatBubble(role, htmlContent) {
  const history = document.getElementById("chatHistory");
  const bubble = document.createElement("div");
  const uniqueId = "bubble_" + Math.random().toString(36).substr(2, 9);
  bubble.id = uniqueId;
  bubble.className = `chat-bubble ${role}`;

  const roleLabel = role === "sam" ? "SAM OPERATOR" : "USER";
  const metaClass = role === "sam" ? "meta-sam" : "";

  bubble.innerHTML = `
    <div class="meta">
      <span class="${metaClass}">${roleLabel}</span>
      <span>${new Date().toLocaleTimeString()}</span>
    </div>
    <div class="msg-content">${htmlContent}</div>
  `;
  history.appendChild(bubble);
  history.scrollTop = history.scrollHeight;
  return uniqueId;
}

function confirmClearChat() {
  if (confirm("Clear all conversation history?")) {
    fetch("/api/chat/clear", { method: "POST" })
      .then(() => {
        document.getElementById("chatHistory").innerHTML = `
          <div class="chat-bubble sam">
            <div class="meta"><span class="meta-sam">SAM OPERATOR</span><span>READY</span></div>
            <div class="msg-content">Conversation history cleared. Ready for your next objective.</div>
          </div>
        `;
      });
  }
}

function handleChatFileUpload(input) {
  if (!input.files || input.files.length === 0) return;
  const file = input.files[0];
  const formData = new FormData();
  formData.append("file", file);
  formData.append("workspace", "default_project");

  fetch("/api/documents/upload", { method: "POST", body: formData })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        appendChatBubble("sam", `Uploaded file <strong>${escapeHtml(file.name)}</strong> (${(data.size_bytes/1024).toFixed(1)} KB) to workspace <code>default_project</code>.`);
      } else {
        alert("Upload error: " + data.error);
      }
    });
}

// ---------------------------------------------------------
// Task Polling & Controls
// ---------------------------------------------------------
function pollTaskStatus(taskId) {
  currentTaskId = taskId;
  const timer = setInterval(async () => {
    try {
      const res = await fetch(`/api/tasks/${taskId}`);
      if (res.ok) {
        const task = await res.json();
        renderActiveTask(task);

        if (task.status === "COMPLETED" || task.status === "FAILED" || task.status === "STOPPED") {
          clearInterval(timer);
          const details = task.verification_result ? task.verification_result.details : (task.error_details || "Task finalized.");
          appendChatBubble("sam", `Task [${task.task_id}] <strong>${task.status}</strong>: ${escapeHtml(details)}`);
          loadTaskHistory();
        }

        if (task.status === "WAITING_APPROVAL") {
          showApprovalModal(task);
        }
      }
    } catch (e) {
      console.warn("Task poll error:", e);
    }
  }, 1000);
}

function renderActiveTask(task) {
  document.getElementById("activeTaskId").textContent = task.task_id;
  document.getElementById("activeTaskObjective").textContent = task.objective;
  document.getElementById("activeTaskPlanner").textContent = `Planned by: ${task.context_data ? (task.context_data.planned_by || "Local Planner") : "Local Planner"}`;

  const statusBadge = document.getElementById("activeTaskStatus");
  statusBadge.textContent = task.status;
  statusBadge.className = `badge ${task.status.toLowerCase()}`;

  const progress = task.progress_percent || 0;
  document.getElementById("taskProgressBar").style.width = `${progress}%`;

  const stepsList = document.getElementById("taskStepsList");
  stepsList.innerHTML = "";

  (task.steps || []).forEach((s, idx) => {
    const item = document.createElement("div");
    item.className = "step-item";
    item.innerHTML = `
      <div class="step-info">
        <div class="step-title">${idx + 1}. ${escapeHtml(s.title)}</div>
        <div class="step-desc">Tool: <code>${escapeHtml(s.tool_name)}</code> • Risk: ${s.risk_level}</div>
      </div>
      <span class="badge ${s.status.toLowerCase()}">${s.status}</span>
    `;
    stepsList.appendChild(item);
  });
}

async function loadTaskHistory() {
  try {
    const res = await fetch("/api/tasks/history");
    if (res.ok) {
      const data = await res.json();
      const body = document.getElementById("taskHistoryBody");
      body.innerHTML = "";
      if (data.tasks.length === 0) {
        body.innerHTML = `<tr><td colspan="5" style="color: var(--text-muted); text-align: center;">No task history recorded yet.</td></tr>`;
        return;
      }
      data.tasks.forEach(t => {
        const row = document.createElement("tr");
        const dt = t.created_at ? new Date(t.created_at * 1000).toLocaleTimeString() : "--";
        row.innerHTML = `
          <td style="font-family: var(--font-mono); font-size: 11px; color: var(--accent-cyan);">${escapeHtml(t.task_id)}</td>
          <td>${escapeHtml(t.objective)}</td>
          <td><span class="badge ${t.status.toLowerCase()}">${t.status}</span></td>
          <td>${t.steps_count || 0}</td>
          <td>${dt}</td>
        `;
        body.appendChild(row);
      });
    }
  } catch (e) {
    console.warn("Task history error:", e);
  }
}

async function handlePauseTask() {
  if (!currentTaskId) return;
  await fetch(`/api/tasks/${currentTaskId}/pause`, { method: "POST" });
}

async function handleResumeTask() {
  if (!currentTaskId) return;
  await fetch(`/api/tasks/${currentTaskId}/resume`, { method: "POST" });
}

async function handleStopTask() {
  if (!currentTaskId) return;
  await fetch(`/api/tasks/${currentTaskId}/stop`, { method: "POST" });
}

// ---------------------------------------------------------
// User Approval Modal
// ---------------------------------------------------------
function showApprovalModal(task) {
  const modal = document.getElementById("approvalModal");
  if (!modal) return;
  modal.style.display = "flex";
  const step = task.pending_approval_step;
  document.getElementById("modalActionName").textContent = step ? step.title : "High-Risk Action";
  document.getElementById("modalRiskLevel").textContent = step ? step.risk_level : "HIGH";
  document.getElementById("modalDetails").textContent = step ? JSON.stringify(step.tool_args, null, 2) : "Confirmation required.";
}

async function approveAction() {
  if (!currentTaskId) return;
  await fetch(`/api/tasks/${currentTaskId}/approve`, { method: "POST" });
  document.getElementById("approvalModal").style.display = "none";
}

async function rejectAction() {
  if (!currentTaskId) return;
  await fetch(`/api/tasks/${currentTaskId}/reject`, { method: "POST" });
  document.getElementById("approvalModal").style.display = "none";
}

// ---------------------------------------------------------
// Quick Workflow Launcher
// ---------------------------------------------------------
function launchWorkflow(code) {
  const prompts = {
    A: "Open VS Code, create a Python project, write a script, run it and fix errors.",
    B: "Open a selected video, create a vertical 1080p edit, add generated subtitles and export the finished video.",
    C: "Open a browser, research a topic, collect information and prepare a report.",
    D: "Check my laptop's CPU, RAM, GPU and disk usage and explain any issues.",
    E: "Open my selected PDF, summarize it and answer questions about its contents."
  };
  const goal = prompts[code];
  if (!goal) return;

  chatInput.value = goal;
  handleSendChat();

  // Switch to tasks tab
  const tab = document.querySelector('[data-tab="paneTasks"]');
  if (tab) tab.click();
}

// ---------------------------------------------------------
// Voice Controls & Device Selection
// ---------------------------------------------------------
async function refreshAudioDevices() {
  try {
    const res = await fetch("/api/voice/devices");
    if (res.ok) {
      const data = await res.json();
      const select = document.getElementById("voiceDeviceSelect");
      select.innerHTML = "";

      if (data.devices.length === 0) {
        select.innerHTML = `<option value="-1">No input audio devices found</option>`;
        return;
      }

      data.devices.forEach(d => {
        const opt = document.createElement("option");
        opt.value = d.id;
        let label = `[ID ${d.id}] ${d.name}`;
        if (d.is_airdopes) label = `🎧 boAt Airdopes 131 (${d.name})`;
        else if (d.is_intel) label = `💻 Laptop Onboard (${d.name})`;
        if (d.is_default) label += " • Default";
        opt.textContent = label;
        if (d.is_airdopes || d.is_default) opt.selected = true;
        select.appendChild(opt);
      });
    }
  } catch (e) {
    console.warn("Failed to load audio devices:", e);
  }
}

let transcriptState = "IDLE"; // "IDLE" | "VERIFIED_RECORDING" | "REJECTED_RECORDING" | "MANUAL_TEXT_INPUT"

async function handleRecordVoice() {
  const select = document.getElementById("voiceDeviceSelect");
  const devId = select ? parseInt(select.value) : null;
  const durSelect = document.getElementById("voiceDurationSelect");
  const duration = durSelect ? parseFloat(durSelect.value) : 6.0;

  const btn = document.getElementById("btnRecordVoice");
  const status = document.getElementById("voiceStatusText");
  const meterFill = document.getElementById("micMeterFill");

  btn.disabled = true;
  btn.textContent = `🎙️ RECORDING (${duration}s)...`;
  status.textContent = "Listening to microphone...";
  meterFill.style.width = "75%";

  try {
    const res = await fetch("/api/voice/record", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: devId > -1 ? devId : null, duration: duration })
    });
    const data = await res.json();

    btn.disabled = false;
    btn.textContent = "🎙️ START RECORDING";
    meterFill.style.width = "0%";

    if (data.success) {
      const transcriptBox = document.getElementById("transcriptTextarea");
      transcriptBox.value = data.transcript;

      const badge = document.getElementById("transcriptReliability");
      if (data.is_valid && (data.reliable || data.ready_for_submission)) {
        badge.className = "badge completed";
        badge.textContent = "VERIFIED SIGNAL";
        transcriptState = "VERIFIED_RECORDING";
      } else {
        badge.className = "badge waiting_approval";
        badge.textContent = "REJECTED / LOW SIGNAL";
        transcriptState = "REJECTED_RECORDING";
      }
      status.textContent = data.message;
    } else {
      status.textContent = "Recording error: " + data.error;
    }
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "🎙️ START RECORDING";
    status.textContent = "Recording failed: " + e.message;
  }
}

// Attach manual input listener to transcript textarea
const transcriptEl = document.getElementById("transcriptTextarea");
if (transcriptEl) {
  transcriptEl.addEventListener("input", () => {
    transcriptState = "MANUAL_TEXT_INPUT";
    const badge = document.getElementById("transcriptReliability");
    if (badge) {
      badge.className = "badge running";
      badge.textContent = "MANUAL INPUT (EDITED)";
    }
    const status = document.getElementById("voiceStatusText");
    if (status) {
      status.textContent = "Transcript manually edited. Review and submit.";
    }
  });
}

function handlePtt(pressed) {
  fetch(`/api/voice/push_to_talk?pressed=${pressed}`, { method: "POST" });
  const status = document.getElementById("voiceStatusText");
  if (status) status.textContent = pressed ? "PTT ACTIVE (Speaking...)" : "PTT Released";
}

function handleExecuteTranscript() {
  const transcriptBox = document.getElementById("transcriptTextarea");
  const transcript = transcriptBox ? transcriptBox.value.trim() : "";
  if (!transcript) {
    alert("Transcription is empty. Speak or type a command first.");
    return;
  }

  // Reject accidental hallucinated trigger words
  const cleanWord = transcript.toLowerCase().replace(/[.,!?;:]/g, "").trim();
  const blockedTriggers = ["you", "thank you", "thanks", "bye", "okay", "so", "subscribe"];
  if (blockedTriggers.includes(cleanWord)) {
    alert(`Accidental phrase "${transcript}" cannot initiate task planning.`);
    return;
  }

  // Debounce submission button
  const btnExec = document.getElementById("btnExecuteTranscript");
  if (btnExec) {
    btnExec.disabled = true;
    setTimeout(() => { if (btnExec) btnExec.disabled = false; }, 1200);
  }

  // Route to Chat
  chatInput.value = transcript;
  handleSendChat();

  const tab = document.querySelector('[data-tab="paneChat"]');
  if (tab) tab.click();
}

// ---------------------------------------------------------
// Live Computer Preview & Window Monitoring
// ---------------------------------------------------------
function refreshLiveScreen() {
  const img = document.getElementById("liveScreenImg");
  if (img) {
    img.src = `/api/computer/screenshot/image?t=${Date.now()}`;
  }
}

function toggleScreenAutoRefresh(enabled) {
  autoRefreshScreen = enabled;
  if (screenRefreshTimer) clearInterval(screenRefreshTimer);
  if (enabled) {
    screenRefreshTimer = setInterval(() => {
      const pane = document.getElementById("paneComputer");
      if (pane && pane.classList.contains("active")) {
        refreshLiveScreen();
        fetchActiveWindow();
      }
    }, 2000);
  }
}
toggleScreenAutoRefresh(true);

async function fetchActiveWindow() {
  try {
    const res = await fetch("/api/computer/active_window");
    if (res.ok) {
      const data = await res.json();
      document.getElementById("activeWinTitle").textContent = data.title || "Windows Desktop";
      document.getElementById("activeWinPid").textContent = data.pid || "--";
      document.getElementById("activeWinHwnd").textContent = data.hwnd || "--";
      if (data.rect) {
        document.getElementById("activeWinRect").textContent = `${data.rect.width}x${data.rect.height} at (${data.rect.x}, ${data.rect.y})`;
      }
      const stopStatus = document.getElementById("statusEmergencyStop");
      if (stopStatus) {
        stopStatus.textContent = data.emergency_stop_active ? "STOPPED (Blocked)" : "NORMAL";
        stopStatus.style.color = data.emergency_stop_active ? "var(--accent-rose)" : "var(--accent-emerald)";
      }
    }
  } catch (e) {
    console.warn("Active window fetch error:", e);
  }
}

// ---------------------------------------------------------
// Coding Agent Workspace
// ---------------------------------------------------------
async function loadCodingWorkspaces() {
  try {
    const res = await fetch("/api/coding/workspaces");
    if (res.ok) {
      const data = await res.json();
      const sel = document.getElementById("codeWorkspaceSelect");
      sel.innerHTML = "";
      data.workspaces.forEach(w => {
        const opt = document.createElement("option");
        opt.value = w;
        opt.textContent = w;
        sel.appendChild(opt);
      });
      loadCodingFiles();
    }
  } catch (e) {
    console.warn("Coding workspace error:", e);
  }
}

async function loadCodingFiles() {
  const ws = document.getElementById("codeWorkspaceSelect").value;
  if (!ws) return;
  try {
    const res = await fetch(`/api/coding/files?workspace=${encodeURIComponent(ws)}`);
    if (res.ok) {
      const data = await res.json();
      const sel = document.getElementById("codeFileSelect");
      sel.innerHTML = `<option value="">Select a file...</option>`;
      (data.files || []).forEach(f => {
        const opt = document.createElement("option");
        opt.value = f;
        opt.textContent = f;
        sel.appendChild(opt);
      });
    }
  } catch (e) {
    console.warn("Files load error:", e);
  }
}

async function loadCodingFileContent() {
  const ws = document.getElementById("codeWorkspaceSelect").value;
  const file = document.getElementById("codeFileSelect").value;
  if (!ws || !file) return;

  try {
    const res = await fetch(`/api/coding/read?workspace=${encodeURIComponent(ws)}&filename=${encodeURIComponent(file)}`);
    if (res.ok) {
      const data = await res.json();
      document.getElementById("codeEditor").value = data.content;
    }
  } catch (e) {
    console.warn("File read error:", e);
  }
}

async function saveCodingFile() {
  const ws = document.getElementById("codeWorkspaceSelect").value;
  const file = document.getElementById("codeFileSelect").value;
  const content = document.getElementById("codeEditor").value;

  const targetFile = file || prompt("Enter filename (e.g. main.py):", "main.py");
  if (!targetFile) return;

  try {
    const res = await fetch("/api/coding/write", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace: ws, filename: targetFile, content: content })
    });
    const data = await res.json();
    if (data.success) {
      alert(`File '${targetFile}' saved successfully.`);
      loadCodingFiles();
    } else {
      alert("Save failed: " + data.error);
    }
  } catch (e) {
    alert("Save error: " + e.message);
  }
}

async function runCodingScript() {
  const ws = document.getElementById("codeWorkspaceSelect").value;
  const file = document.getElementById("codeFileSelect").value || "main.py";
  const consoleEl = document.getElementById("codeTerminalConsole");

  consoleEl.textContent = `[EXECUTING] python ${file} in workspace '${ws}'...\n`;

  try {
    const res = await fetch("/api/coding/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace: ws, filename: file })
    });
    const data = await res.json();

    let out = `[COMPLETED] Exit Code: ${data.exit_code} (Duration: ${data.duration}s)\n\n`;
    if (data.stdout) out += `--- STDOUT ---\n${data.stdout}\n`;
    if (data.stderr) out += `--- STDERR ---\n${data.stderr}\n`;
    if (!data.stdout && !data.stderr) out += "Process finished with no console output.\n";
    consoleEl.textContent = out;
  } catch (e) {
    consoleEl.textContent = `[EXECUTION ERROR] ${e.message}\n`;
  }
}

// ---------------------------------------------------------
// Video Editor
// ---------------------------------------------------------
async function loadVideoExports() {
  try {
    const res = await fetch("/api/video/exports");
    if (res.ok) {
      const data = await res.json();
      const body = document.getElementById("videoExportsBody");
      body.innerHTML = "";
      if (data.exports.length === 0) {
        body.innerHTML = `<tr><td colspan="2" style="color: var(--text-muted); text-align: center;">No video exports yet.</td></tr>`;
        return;
      }
      data.exports.forEach(v => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td style="font-family: var(--font-mono); font-size: 11.5px; color: var(--accent-cyan);">${escapeHtml(v.name)}</td>
          <td>${v.size_mb} MB</td>
        `;
        body.appendChild(row);
      });
    }
  } catch (e) {
    console.warn("Video exports error:", e);
  }
}

async function handleRenderVideo() {
  const status = document.getElementById("videoRenderStatus");
  status.style.display = "block";
  status.textContent = "Rendering 1080x1920 vertical video with subtitles (FFmpeg/OpenCV)...";

  try {
    const res = await fetch("/api/video/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_width: 1080, target_height: 1920 })
    });
    const data = await res.json();
    if (data.success) {
      status.textContent = `Render verified: ${data.output_path} (${data.width}x${data.height}, ${data.duration}s)`;
      loadVideoExports();
    } else {
      status.textContent = "Render error: " + (data.error || "Execution failed");
    }
  } catch (e) {
    status.textContent = "Render execution error: " + e.message;
  }
}

// ---------------------------------------------------------
// Browser Research Agent
// ---------------------------------------------------------
async function handleBrowserResearch() {
  const query = document.getElementById("browserQueryInput").value.trim();
  const url = document.getElementById("browserUrlInput").value.trim();
  const consoleEl = document.getElementById("browserReportConsole");

  if (!query && !url) {
    alert("Please enter a research topic or target URL.");
    return;
  }

  consoleEl.textContent = `Navigating and extracting information for '${query || url}'...\n`;

  try {
    const res = await fetch("/api/browser/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query, url: url || null })
    });
    const data = await res.json();
    if (data.success) {
      consoleEl.innerHTML = `
<strong>Target:</strong> ${escapeHtml(data.url)}<br>
<strong>Title:</strong> ${escapeHtml(data.title)}<br><br>
<strong>Extracted Content Summary:</strong><br>
${escapeHtml(data.content_sample)}
      `;
    } else {
      consoleEl.textContent = "Research error: " + data.error;
    }
  } catch (e) {
    consoleEl.textContent = "Connection error: " + e.message;
  }
}

// ---------------------------------------------------------
// Documents & Files
// ---------------------------------------------------------
async function loadDocFiles() {
  try {
    const res = await fetch("/api/documents/list");
    if (res.ok) {
      const data = await res.json();
      const body = document.getElementById("docFilesBody");
      body.innerHTML = "";
      if (data.documents.length === 0) {
        body.innerHTML = `<tr><td colspan="4" style="color: var(--text-muted); text-align: center;">No documents in workspace. Upload a file above.</td></tr>`;
        return;
      }
      data.documents.forEach(d => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td style="font-family: var(--font-mono); font-size: 11.5px; color: var(--accent-cyan);">${escapeHtml(d.name)}</td>
          <td>${d.extension}</td>
          <td>${d.size_kb} KB</td>
          <td><button class="btn-secondary" style="padding: 2px 8px; font-size: 11px;" onclick="handleSummarizeDoc('${escapeHtml(d.name)}')">Summarize</button></td>
        `;
        body.appendChild(row);
      });
    }
  } catch (e) {
    console.warn("Docs load error:", e);
  }
}

function handleDocUpload(input) {
  if (!input.files || input.files.length === 0) return;
  const file = input.files[0];
  const formData = new FormData();
  formData.append("file", file);
  formData.append("workspace", "default_project");

  fetch("/api/documents/upload", { method: "POST", body: formData })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        alert(`File '${file.name}' uploaded.`);
        loadDocFiles();
      }
    });
}

async function handleSummarizeDoc(filename) {
  const consoleEl = document.getElementById("docSummaryConsole");
  consoleEl.textContent = `Extracting and analyzing '${filename}' using DocumentEngine...`;

  try {
    const res = await fetch("/api/documents/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace: "default_project", filename: filename })
    });
    const data = await res.json();
    if (data.success) {
      consoleEl.innerHTML = `
<strong>Document:</strong> ${escapeHtml(data.filename)} (${data.total_pages || 1} pages)<br>
<strong>Parser Backend:</strong> ${escapeHtml(data.parser || "pypdf/docx")}<br><br>
<strong>Executive Summary:</strong><br>
${escapeHtml(data.summary)}
      `;
    } else {
      consoleEl.textContent = "Summarization error: " + data.error;
    }
  } catch (e) {
    consoleEl.textContent = "Summarization connection error: " + e.message;
  }
}

// ---------------------------------------------------------
// Memory Store CRUD
// ---------------------------------------------------------
async function loadAllMemories() {
  try {
    const res = await fetch("/api/memory");
    if (res.ok) {
      const data = await res.json();
      renderMemoriesTable(data.memories || []);
    }
  } catch (e) {
    console.warn("Memory load error:", e);
  }
}

async function searchMemories(query) {
  try {
    const res = await fetch(`/api/memory/search?query=${encodeURIComponent(query)}`);
    if (res.ok) {
      const data = await res.json();
      renderMemoriesTable(data.memories || []);
    }
  } catch (e) {
    console.warn("Memory search error:", e);
  }
}

function renderMemoriesTable(memories) {
  const body = document.getElementById("memoriesBody");
  body.innerHTML = "";
  if (memories.length === 0) {
    body.innerHTML = `<tr><td colspan="4" style="color: var(--text-muted); text-align: center;">No stored memories match query.</td></tr>`;
    return;
  }
  memories.forEach(m => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><span class="badge pending">${escapeHtml(m.category)}</span></td>
      <td style="font-family: var(--font-mono); font-size: 11.5px; color: var(--accent-cyan);">${escapeHtml(m.key)}</td>
      <td style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(String(m.value))}</td>
      <td><button class="btn-danger" style="padding: 2px 8px; font-size: 10px;" onclick="handleDeleteMemory('${escapeHtml(m.key)}')">Delete</button></td>
    `;
    body.appendChild(row);
  });
}

async function saveNewMemory() {
  const cat = document.getElementById("newMemCategory").value.trim() || "preferences";
  const key = document.getElementById("newMemKey").value.trim();
  const val = document.getElementById("newMemVal").value.trim();

  if (!key || !val) {
    alert("Please enter a Key and Value.");
    return;
  }

  try {
    const res = await fetch("/api/memory", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category: cat, key: key, value: val })
    });
    if (res.ok) {
      document.getElementById("newMemKey").value = "";
      document.getElementById("newMemVal").value = "";
      loadAllMemories();
    }
  } catch (e) {
    alert("Failed to save memory: " + e.message);
  }
}

async function handleDeleteMemory(key) {
  if (confirm(`Delete memory item '${key}'?`)) {
    await fetch(`/api/memory/${encodeURIComponent(key)}`, { method: "DELETE" });
    loadAllMemories();
  }
}

// ---------------------------------------------------------
// Settings, Models & Audit
// ---------------------------------------------------------
async function loadSettingsAndAudit() {
  try {
    const statusRes = await fetch("/api/models/status");
    if (statusRes.ok) {
      const data = await statusRes.json();
      document.getElementById("settingsOllamaStatus").textContent = data.ollama_online ? "ONLINE (127.0.0.1:11434)" : "UNAVAILABLE (Offline)";
      document.getElementById("settingsOllamaStatus").style.color = data.ollama_online ? "var(--accent-emerald)" : "var(--accent-rose)";
      document.getElementById("settingsActiveModel").textContent = data.configured_model || "qwen2.5:3b";
      document.getElementById("telemetryModel").textContent = `Model: ${data.configured_model || "Qwen"}`;
    }

    const auditRes = await fetch("/api/security/audit_logs");
    if (auditRes.ok) {
      const data = await auditRes.json();
      const consoleEl = document.getElementById("auditLogsConsole");
      consoleEl.innerHTML = "";
      (data.logs || []).forEach(l => {
        const line = document.createElement("div");
        line.style.borderBottom = "1px solid var(--border-subtle)";
        line.style.padding = "3px 0";
        line.textContent = `[${l.datetime || ""}] [${l.risk_level || "LOW"}] ${l.event_type || l.action}: ${JSON.stringify(l.details || {})}`;
        consoleEl.appendChild(line);
      });
    }
  } catch (e) {
    console.warn("Settings load error:", e);
  }
}

async function handleSwitchModel() {
  const modelName = document.getElementById("settingsModelSelect").value;
  try {
    const res = await fetch("/api/models/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_name: modelName })
    });
    const data = await res.json();
    alert(`Active model switched to: ${data.selected_model}`);
    loadSettingsAndAudit();
  } catch (e) {
    alert("Switch model error: " + e.message);
  }
}

async function triggerEmergencyStop() {
  try {
    const res = await fetch("/api/emergency_stop", { method: "POST" });
    isEmergencyStopped = true;
    const btn = document.getElementById("emergencyStopBtn");
    btn.textContent = "HALTED";
    btn.style.background = "var(--accent-rose)";
    btn.style.color = "#fff";
    alert("GLOBAL EMERGENCY STOP ACTIVATED: All computer actions halted.");
    fetchActiveWindow();
  } catch (e) {
    alert("Emergency stop error: " + e.message);
  }
}
document.getElementById("emergencyStopBtn").addEventListener("click", triggerEmergencyStop);

async function handleResetEmergencyStop() {
  try {
    await fetch("/api/security/reset_emergency_stop", { method: "POST" });
    isEmergencyStopped = false;
    const btn = document.getElementById("emergencyStopBtn");
    btn.textContent = "⚠ EMERGENCY STOP";
    btn.style.background = "rgba(244, 63, 94, 0.15)";
    btn.style.color = "var(--accent-rose)";
    alert("Emergency stop reset to NORMAL. Automated execution re-enabled.");
    fetchActiveWindow();
  } catch (e) {
    alert("Reset error: " + e.message);
  }
}

// ---------------------------------------------------------
// Helper: HTML Escaping
// ---------------------------------------------------------
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
