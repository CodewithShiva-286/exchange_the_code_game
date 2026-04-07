/**
 * Admin Dashboard — script.js
 *
 * Fully backend-connected. No hardcoded data.
 * Polls GET /admin/teams every 3s for live updates.
 * Fetches GET /admin/groups for dropdown population.
 * Assigns groups via POST /admin/assign-group.
 * Starts round via POST /admin/start.
 */

// ── Config ──────────────────────────────────────────────────────────────────
let pollInterval = null;
let cachedGroups = [];

// ── DOM References ──────────────────────────────────────────────────────────
const teamContainer = document.getElementById("teamContainer");
const emptyState = document.getElementById("emptyState");
const teamCountBadge = document.getElementById("teamCountBadge");
const serverDot = document.getElementById("serverDot");
const serverLabel = document.getElementById("serverLabel");

// ── Toast Notifications ─────────────────────────────────────────────────────
function showToast(message, type = "info") {
   const container = document.getElementById("toastContainer");
   const toast = document.createElement("div");
   toast.className = `toast toast-${type}`;
   toast.textContent = message;
   container.appendChild(toast);
   setTimeout(() => toast.remove(), 3000);
}

// ── Modal ────────────────────────────────────────────────────────────────────
function showModal(title, message) {
   document.getElementById("modalTitle").textContent = title;
   document.getElementById("modalMessage").textContent = message;
   document.getElementById("errorModal").classList.add("visible");
}

function closeModal() {
   document.getElementById("errorModal").classList.remove("visible");
}

// ── API Helpers ──────────────────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
   try {
      const res = await fetch(`${BASE_URL}${path}`, {
         headers: { "Content-Type": "application/json" },
         ...options,
      });
      const data = await res.json();
      if (!res.ok) {
         throw new Error(data.detail || `HTTP ${res.status}`);
      }
      return data;
   } catch (err) {
      if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
         setServerStatus(false);
      }
      throw err;
   }
}

function setServerStatus(online) {
   serverDot.className = "status-dot " + (online ? "online" : "offline");
   serverLabel.textContent = online ? "Server online" : "Server offline";
}

// ── Fetch Groups (for dropdown) ─────────────────────────────────────────────
async function fetchGroups() {
   try {
      cachedGroups = await apiFetch("/admin/groups");
   } catch (err) {
      console.error("Failed to fetch groups:", err);
      cachedGroups = [];
   }
}

// ── Fetch Teams & Render ────────────────────────────────────────────────────
async function fetchAndRender() {
   try {
      const teams = await apiFetch("/admin/teams");
      setServerStatus(true);
      renderTeams(teams);
   } catch (err) {
      console.error("Failed to fetch teams:", err);
   }
}

// ── Render Teams ────────────────────────────────────────────────────────────
function renderTeams(teams) {
   teamCountBadge.textContent = `${teams.length} Team${teams.length !== 1 ? "s" : ""}`;

   if (teams.length === 0) {
      emptyState.classList.remove("hidden");
      teamContainer.innerHTML = "";
      return;
   }

   emptyState.classList.add("hidden");
   teamContainer.innerHTML = "";

   for (const team of teams) {
      const card = document.createElement("div");
      card.className = "team-card";
      card.id = `team-${team.team_id}`;

      // Determine card state (for top border color)
      const connectedCount = team.players.filter(p => p.connected).length;
      if (team.status === "active" || team.current_phase !== "waiting") {
         card.classList.add("active");
      } else if (connectedCount === 2) {
         card.classList.add("ready");
      } else if (connectedCount === 1) {
         card.classList.add("partial");
      }

      // Phase badge
      const phase = team.current_phase || "waiting";
      const phaseLabel = phase.replace("_", " ").toUpperCase();

      // Player rows
      let playersHTML = "";
      for (let slot = 1; slot <= 2; slot++) {
         const player = team.players.find(p => p.slot === slot);
         if (player) {
            const dotClass = player.connected ? "online" : "offline";
            playersHTML += `
               <div class="player-row">
                  <span class="player-dot ${dotClass}"></span>
                  <span class="player-label">P${slot}</span>
                  <span class="player-name">${escapeHtml(player.name)}</span>
               </div>`;
         } else {
            playersHTML += `
               <div class="player-row">
                  <span class="player-dot offline"></span>
                  <span class="player-label">P${slot}</span>
                  <span class="player-empty">Empty</span>
               </div>`;
         }
      }

      // Group assignment dropdown
      const currentGroup = team.group_id;
      let groupOptions = `<option value="">Assign Group...</option>`;
      for (const g of cachedGroups) {
         const selected = g.group_id === currentGroup ? "selected" : "";
         const problemLabels = g.problems.map(p => p.problem_id).join(", ");
         groupOptions += `<option value="${g.group_id}" ${selected}>${g.group_id} (${problemLabels})</option>`;
      }

      card.innerHTML = `
         <div class="card-header">
            <h3 style="display:flex; align-items:center; gap:8px;">
                ${escapeHtml(team.team_id)}
                <button class="btn btn-outline" style="padding:2px 6px; font-size:10px;" onclick="navigator.clipboard.writeText('${escapeHtml(team.team_id)}'); showToast('Team ID copied!', 'success')">Copy</button>
            </h3>
            <span class="phase-badge phase-${phase}">${phaseLabel}</span>
         </div>
         <p style="font-size: 11px; color: var(--text-secondary); margin-top: -12px; margin-bottom: 12px;">Share this Team ID with players</p>

         <div class="players">${playersHTML}</div>

         <div class="group-section">
            <div class="group-label">Problem Group</div>
            ${currentGroup
               ? `<div class="group-value">${escapeHtml(currentGroup)}</div>`
               : `<div class="group-value none">Not assigned</div>`
            }
            <select class="group-select" onchange="assignGroup('${escapeHtml(team.team_id)}', this.value)" id="select-${team.team_id}">
               ${groupOptions}
            </select>
         </div>`;

      teamContainer.appendChild(card);
   }
}

// ── Assign Group ────────────────────────────────────────────────────────────
async function assignGroup(teamId, groupId) {
   if (!groupId) return;
   try {
      await apiFetch("/admin/assign-group", {
         method: "POST",
         body: JSON.stringify({ team_id: teamId, group_id: groupId }),
      });
      showToast(`Group '${groupId}' assigned to ${teamId}`, "success");
      await fetchAndRender();
   } catch (err) {
      showToast(`Failed: ${err.message}`, "error");
      // Revert the select
      await fetchAndRender();
   }
}

// ── Start All ───────────────────────────────────────────────────────────────
async function startAll() {
   try {
      // Pre-flight: check if all teams are ready
      const teams = await apiFetch("/admin/teams");

      if (teams.length === 0) {
         showModal("⚠️ Cannot Start", "No teams exist. Create teams first.");
         return;
      }

      const issues = [];
      for (const t of teams) {
         const connected = t.players.filter(p => p.connected).length;
         if (connected !== 2) {
            issues.push(`${t.team_id}: ${connected}/2 players connected`);
         }
         if (!t.group_id) {
            issues.push(`${t.team_id}: no group assigned`);
         }
      }

      if (issues.length > 0) {
         showModal(
            "⚠️ Cannot Start",
            "Fix these issues first:\n\n" + issues.join("\n")
         );
         return;
      }

      // All clear — start
      await apiFetch("/admin/start", { method: "POST" });
      showToast("Competition started! 🚀", "success");
      await fetchAndRender();
   } catch (err) {
      showModal("⚠️ Error", err.message);
   }
}

// ── New Round ───────────────────────────────────────────────────────────────
async function newRound() {
   if (confirm("Are you sure you want to start a New Round?\n\nThis will keep players, teams, and scores, but clears submissions and assignments.")) {
      try {
         await apiFetch("/admin/new-round", { method: "POST" });
         showToast("New Round initialized!", "success");
         await fetchAndRender();
      } catch (err) {
         showModal("⚠️ Error", err.message);
      }
   }
}

// ── Reset ───────────────────────────────────────────────────────────────────
async function resetAll() {
   if (confirm("Are you sure you want to reset everything? This clears EVERYTHING, including teams, players, and scores. This cannot be undone.")) {
      try {
         await apiFetch("/admin/reset-db", { method: "POST" });
         showToast("Database safely reset!", "success");
         await fetchAndRender();
      } catch(err) {
         showModal("⚠️ Error", err.message);
      }
   }
}

// ── Escape HTML ─────────────────────────────────────────────────────────────
function escapeHtml(str) {
   if (!str) return "";
   const div = document.createElement("div");
   div.textContent = str;
   return div.innerHTML;
}

// ── Navigation & Actions ───────────────────────────────────────────────────
document.getElementById("createTeamBtn").addEventListener("click", async () => {
   try {
      await apiFetch("/admin/create-team", { method: "POST" });
      showToast("Team created successfully!", "success");
      await fetchAndRender();
   } catch (err) {
      showModal("⚠️ Error", err.message);
   }
});

document.getElementById("manageBtn").addEventListener("click", () => {
   window.location.href = "manage-assign.html";
});

document.getElementById("leaderboardBtn").addEventListener("click", () => {
   window.location.href = "leaderboard.html";
});

document.getElementById("refreshBtn").addEventListener("click", async () => {
   showToast("Refreshing...", "info");
   await fetchGroups();
   await fetchAndRender();
});

// ── Polling ─────────────────────────────────────────────────────────────────
function startPolling() {
   if (pollInterval) clearInterval(pollInterval);
   pollInterval = setInterval(fetchAndRender, 3000);
}

// ── Init ────────────────────────────────────────────────────────────────────
(async function init() {
   await fetchGroups();
   await fetchAndRender();
   startPolling();
})();
