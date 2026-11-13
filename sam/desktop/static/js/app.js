// SAM - Desktop Client Controller
let currentTaskId = null;
let isEmergencyStopped = false;

// Tab Switching
document.querySelectorAll(".nav-item").forEach(item => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
    item.classList.add("active");
    const target = item.getAttribute("data-tab");
    const pane = document.getElementById(target);
    if (pane) pane.classList.add("active");
  });
});

// Audio Waveform Animation
const canvas = document.getElementById("waveformCanvas");
if (canvas) {
  const ctx = canvas.getContext("2d");
  let phase = 0;
  function drawWaveform() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.beginPath();
    ctx.strokeStyle = isEmergencyStopped ? "#ff0055" : "#00ffcc";
    ctx.lineWidth = 2;
    for (let x = 0; x < canvas.width; x++) {
      const y = canvas.height / 2 + Math.sin(x * 0.04 + phase) * 16 * Math.sin(phase * 0.5);
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    phase += 0.08;
    requestAnimationFrame(drawWaveform);
  }
  drawWaveform();
}

// Telemetry Polling
async function updateTelemetry() {
  try {
    const res = await fetch("/api/telemetry");
    if (res.ok) {
      const data = await res.json();
      const cpu = data.cpu.cpu_percent_overall;
      const ram = data.ram.used_percent;
      const gpu = data.gpu;

      document.getElementById("telemetryCpu").textContent = `CPU: ${cpu}%`;
      document.getElementById("telemetryRam").textContent = `RAM: ${ram}%`;
      if (gpu && gpu.available) {
        document.getElementById("telemetryGpu").textContent = `RTX 4050: ${gpu.vram_used_mb}MB / ${gpu.vram_total_mb}MB (${gpu.temperature_c}°C)`;
      } else {
        document.getElementById("telemetryGpu").textContent = "GPU: Idle";
      }

      // Detailed settings view if active
      const cpuElem = document.getElementById("diagCpu");
      if (cpuElem) cpuElem.textContent = `${cpu}% (${data.cpu.cores_logical} cores)`;
      const ramElem = document.getElementById("diagRam");
      if (ramElem) ramElem.textContent = `${data.ram.used_gb} GB / ${data.ram.total_gb} GB (${ram}%)`;
      const gpuElem = document.getElementById("diagGpu");
      if (gpuElem && gpu) gpuElem.textContent = `${gpu.name} - ${gpu.vram_free_mb} MB Free, Temp: ${gpu.temperature_c}°C`;
    }
  } catch (e) {
    console.error("Telemetry fetch error:", e);
  }
}
setInterval(updateTelemetry, 2000);
updateTelemetry();

// Emergency Stop Handler
async function triggerEmergencyStop() {
  try {
    const res = await fetch("/api/emergency_stop", { method: "POST" });
    const data = await res.json();
    isEmergencyStopped = true;
    const btn = document.getElementById("emergencyStopBtn");
    btn.textContent = "STOPPED";
    btn.style.background = "#555";
    alert("GLOBAL EMERGENCY STOP ACTIVATED: All automated operations halted.");
  } catch (e) {
    alert("Failed to signal emergency stop: " + e);
  }
}
document.getElementById("emergencyStopBtn").addEventListener("click", triggerEmergencyStop);

// Chat / Goal Submission
async function sendGoal(goalText) {
  const input = document.getElementById("chatInput");
  const text = goalText || input.value.trim();
  if (!text) return;

  appendChat("user", text);
  if (!goalText) input.value = "";

  try {
    const res = await fetch("/api/tasks/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ objective: text })
    });
    const data = await res.json();
    if (data.task_id) {
      currentTaskId = data.task_id;
      appendChat("sam", `Task accepted: [${data.task_id}]. Planning ${data.steps_count} verified steps.`);
      pollTaskStatus(data.task_id);
    } else {
      appendChat("sam", `Error creating task: ${data.error}`);
    }
  } catch (e) {
    appendChat("sam", `Execution error: ${e.message}`);
  }
}

document.getElementById("chatSendBtn").addEventListener("click", () => sendGoal());
document.getElementById("chatInput").addEventListener("keypress", (e) => {
  if (e.key === "Enter") sendGoal();
});

function appendChat(role, msg) {
  const history = document.getElementById("chatHistory");
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}`;
  bubble.innerHTML = `
    <div class="meta">${role.toUpperCase()} • ${new Date().toLocaleTimeString()}</div>
    <div class="msg-content">${msg}</div>
  `;
  history.appendChild(bubble);
  history.scrollTop = history.scrollHeight;
}

// Task Polling
async function pollTaskStatus(taskId) {
  const pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/tasks/${taskId}`);
      if (res.ok) {
        const task = await res.json();
        renderActiveTask(task);

        if (task.status === "COMPLETED" || task.status === "FAILED" || task.status === "STOPPED") {
          clearInterval(pollInterval);
          appendChat("sam", `Task [${task.task_id}] ${task.status}: ${task.verification_result ? task.verification_result.details : (task.error_details || "")}`);
        }

        if (task.status === "WAITING_APPROVAL") {
          showApprovalModal(task);
        }
      }
    } catch (e) {
      console.error("Task poll error:", e);
    }
  }, 1000);
}

function renderActiveTask(task) {
  document.getElementById("activeTaskId").textContent = task.task_id;
  document.getElementById("activeTaskStatus").textContent = task.status;
  document.getElementById("activeTaskStatus").className = `badge ${task.status.toLowerCase()}`;
  document.getElementById("activeTaskObjective").textContent = task.objective;
  document.getElementById("taskProgressBar").style.width = `${task.progress_percent}%`;

  const stepsList = document.getElementById("taskStepsList");
  stepsList.innerHTML = "";
  task.steps.forEach(s => {
    const stepEl = document.createElement("div");
    stepEl.className = "step-item";
    stepEl.innerHTML = `
      <div class="step-info">
        <div class="step-title">${s.step_index + 1}. ${s.title}</div>
        <div class="step-desc">${s.description} • Tool: <code>${s.tool_name}</code></div>
      </div>
      <span class="badge ${s.status.toLowerCase()}">${s.status}</span>
    `;
    stepsList.appendChild(stepEl);
  });
}

function showApprovalModal(task) {
  const modal = document.getElementById("approvalModal");
  if (!modal) return;
  modal.style.display = "flex";
  const step = task.pending_approval_step;
  document.getElementById("modalActionName").textContent = step ? step.title : "High-Risk Operation";
  document.getElementById("modalRiskLevel").textContent = step ? step.risk_level : "HIGH";
  document.getElementById("modalDetails").textContent = step ? JSON.stringify(step.tool_args, null, 2) : "";
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

// Preset Quick Workflow Launchers
function launchWorkflow(code) {
  const prompts = {
    A: "Open VS Code, create a Python project, write a script, run it and fix errors.",
    B: "Open a selected video, create a vertical 1080p edit, add generated subtitles and export the finished video.",
    C: "Open a browser, research a topic, collect information and prepare a report.",
    D: "Check my laptop's CPU, RAM, GPU and disk usage and explain any issues.",
    E: "Open my selected PDF, summarize it and answer questions about its contents."
  };
  sendGoal(prompts[code]);
  // Switch to Active Tasks tab
  const taskTab = document.querySelector('[data-tab="paneTasks"]');
  if (taskTab) taskTab.click();
}

