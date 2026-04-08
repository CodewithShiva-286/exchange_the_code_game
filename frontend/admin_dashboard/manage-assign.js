/**
 * Manage Assignments — manage-assign.js
 *
 * Fully backend-connected.
 * Fetches teams and groups from API, allows creating groups and assigning them.
 */

let allTeams = [];
let allGroups = [];
let allProblems = []; // fetched from /admin/groups -> deduplicated

// ── API Helper ──────────────────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
   const res = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
   });
   const data = await res.json();
   if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
   return data;
}

// ── Load Data ───────────────────────────────────────────────────────────────
async function loadData() {
   try {
      allTeams = await apiFetch("/admin/teams");
      allGroups = await apiFetch("/admin/groups");

      // Fetch all available problems directly from the backend
      const problemList = await apiFetch("/admin/problems");
      allProblems = problemList.map(p => p.problem_id).sort();

      renderTable();
      populateProblemSelects();
   } catch (err) {
      console.error("Failed to load data:", err);
      alert("Failed to connect to backend: " + err.message);
   }
}

// ── Render Assignment Table ─────────────────────────────────────────────────
function renderTable() {
   const table = document.getElementById("assignmentTable");
   table.innerHTML = "";

   if (allTeams.length === 0) {
      table.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#555;padding:32px;">No teams created yet</td></tr>`;
      return;
   }

   for (const team of allTeams) {
      const row = document.createElement("tr");

      // Find group details
      const group = allGroups.find(g => g.group_id === team.group_id);
      const p1 = group ? group.problems.find(p => p.position === 1)?.problem_id : "-";
      const p2 = group ? group.problems.find(p => p.position === 2)?.problem_id : "-";

      // Group select dropdown
      let groupOptions = `<option value="">Select Group...</option>`;
      for (const g of allGroups) {
         const sel = g.group_id === team.group_id ? "selected" : "";
         groupOptions += `<option value="${g.group_id}" ${sel}>${g.group_id}</option>`;
      }

      row.innerHTML = `
         <td><strong>${escapeHtml(team.team_id)}</strong></td>
         <td>
            <select onchange="handleGroupChange('${escapeHtml(team.team_id)}', this.value)">
               ${groupOptions}
            </select>
         </td>
         <td id="p1-${team.team_id}">${p1}</td>
         <td id="p2-${team.team_id}">${p2}</td>
         <td>
            ${team.group_id
               ? `<span class="assigned-tag">✓ Assigned</span>`
               : `<span style="color:#555">—</span>`
            }
         </td>`;

      table.appendChild(row);
   }
}

// ── Handle Group Change in Table ────────────────────────────────────────────
async function handleGroupChange(teamId, groupId) {
   if (!groupId) return;
   try {
      await apiFetch("/admin/assign-group", {
         method: "POST",
         body: JSON.stringify({ team_id: teamId, group_id: groupId }),
      });
      await loadData(); // Refresh
   } catch (err) {
      alert("Failed to assign: " + err.message);
      await loadData(); // Revert UI
   }
}

// ── Populate Problem Selects (Create Group Form) ────────────────────────────
function populateProblemSelects() {
   const p1 = document.getElementById("newP1");
   const p2 = document.getElementById("newP2");

   // Also fetch all available problems from the backend
   fetch(`${BASE_URL}/problem/p001`).catch(() => {}); // ping to check

   p1.innerHTML = `<option value="">-- Select --</option>`;
   p2.innerHTML = `<option value="">-- Select --</option>`;

   for (const pid of allProblems) {
      p1.innerHTML += `<option value="${pid}">${pid}</option>`;
      p2.innerHTML += `<option value="${pid}">${pid}</option>`;
   }
}

// ── Create Group Form Toggle ────────────────────────────────────────────────
document.getElementById("createGroupBtn").addEventListener("click", () => {
   const form = document.getElementById("createGroupForm");
   form.style.display = form.style.display === "none" ? "block" : "none";
});

document.getElementById("cancelGroupBtn").addEventListener("click", () => {
   document.getElementById("createGroupForm").style.display = "none";
   document.getElementById("formError").textContent = "";
});

// ── Submit Create Group ─────────────────────────────────────────────────────
document.getElementById("submitGroupBtn").addEventListener("click", async () => {
   const groupId = document.getElementById("newGroupId").value.trim();
   const p1 = document.getElementById("newP1").value;
   const p2 = document.getElementById("newP2").value;
   const errorEl = document.getElementById("formError");

   if (!groupId || !p1 || !p2) {
      errorEl.textContent = "All fields are required.";
      return;
   }

   if (p1 === p2) {
      errorEl.textContent = "Problems must be different.";
      return;
   }

   try {
      await apiFetch("/admin/create-group", {
         method: "POST",
         body: JSON.stringify({ group_id: groupId, problem_ids: [p1, p2] }),
      });
      errorEl.textContent = "";
      document.getElementById("createGroupForm").style.display = "none";
      document.getElementById("newGroupId").value = "";
      await loadData();
   } catch (err) {
      errorEl.textContent = err.message;
   }
});

// ── Back Button ─────────────────────────────────────────────────────────────
document.getElementById("backBtn").addEventListener("click", () => {
   window.location.href = "index.html";
});

// ── Escape HTML ─────────────────────────────────────────────────────────────
function escapeHtml(str) {
   if (!str) return "";
   const div = document.createElement("div");
   div.textContent = str;
   return div.innerHTML;
}

// ── Init ────────────────────────────────────────────────────────────────────
loadData();
