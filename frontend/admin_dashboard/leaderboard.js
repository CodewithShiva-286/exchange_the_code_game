const HOST = window.location.hostname || "localhost";
const HTTP_PROTOCOL = window.location.protocol === "file:" ? "http:" : window.location.protocol;
const WS_PROTOCOL = window.location.protocol === "https:" ? "wss:" : "ws:";
const BASE_URL = `${HTTP_PROTOCOL}//${HOST}:8000`;
const WS_URL = `${WS_PROTOCOL}//${HOST}:8000`;
const ADMIN_WS_KEY = window.localStorage.getItem("admin_ws_key") || "techfest-admin-secret-2026";

let adminSocket = null;
let reconnectTimer = null;

const leaderboardTableBody = document.getElementById("leaderboardTableBody");
const emptyState = document.getElementById("emptyState");
const wsStatus = document.getElementById("wsStatus");

function setSocketStatus(label, mode = "") {
   wsStatus.textContent = label;
   wsStatus.className = `status-badge${mode ? ` ${mode}` : ""}`;
}

async function loadLeaderboard() {
   const response = await fetch(`${BASE_URL}/admin/leaderboard`);
   const data = await response.json();
   console.log("Leaderboard API:", data);

   if (!response.ok) {
      throw new Error(data.detail || `HTTP ${response.status}`);
   }

   renderLeaderboard(Array.isArray(data) ? data : []);
}

function renderLeaderboard(data) {
   const sorted = [...data].sort((a, b) => {
      const scoreDiff = Number(b.total_score || 0) - Number(a.total_score || 0);
      if (scoreDiff !== 0) {
         return scoreDiff;
      }
      return String(a.team_id).localeCompare(String(b.team_id));
   });

   leaderboardTableBody.innerHTML = "";
   emptyState.classList.toggle("hidden", sorted.length > 0);

   sorted.forEach((team, index) => {
      const row = document.createElement("tr");
      if (index === 0) row.classList.add("rank-1");
      if (index === 1) row.classList.add("rank-2");
      if (index === 2) row.classList.add("rank-3");

      row.innerHTML = `
         <td><span class="rank-chip">${index + 1}</span></td>
         <td class="team-name">${escapeHtml(team.team_id)}</td>
         <td class="score-value">${Number(team.total_score || 0)}</td>
      `;
      leaderboardTableBody.appendChild(row);
   });
}

function connectAdminSocket() {
   if (adminSocket && (adminSocket.readyState === WebSocket.OPEN || adminSocket.readyState === WebSocket.CONNECTING)) {
      return;
   }

   setSocketStatus("Connecting...");
   adminSocket = new WebSocket(`${WS_URL}/ws/admin?key=${encodeURIComponent(ADMIN_WS_KEY)}`);

   adminSocket.addEventListener("open", () => {
      setSocketStatus("Live updates on", "live");
   });

   adminSocket.addEventListener("message", (event) => {
      let message;
      try {
         message = JSON.parse(event.data);
      } catch (error) {
         console.error("Invalid admin WS payload:", error);
         return;
      }

      switch (message.event) {
         case "ADMIN_CONNECTED":
            setSocketStatus("Live updates on", "live");
            break;
         case "LEADERBOARD_UPDATE":
            console.log("WS Leaderboard Update:", message.data);
            renderLeaderboard(Array.isArray(message.data?.leaderboard) ? message.data.leaderboard : []);
            break;
         case "PONG":
            break;
         default:
            console.debug("Unhandled admin WS event:", message.event);
      }
   });

   adminSocket.addEventListener("close", () => {
      setSocketStatus("Live updates reconnecting...", "offline");
      if (reconnectTimer) {
         clearTimeout(reconnectTimer);
      }
      reconnectTimer = setTimeout(connectAdminSocket, 3000);
   });

   adminSocket.addEventListener("error", () => {
      setSocketStatus("Live updates unavailable", "offline");
   });
}

function escapeHtml(str) {
   if (!str) return "";
   const div = document.createElement("div");
   div.textContent = str;
   return div.innerHTML;
}

document.getElementById("backBtn").addEventListener("click", () => {
   window.location.href = "index.html";
});

window.onload = async function () {
   try {
      await loadLeaderboard();
   } catch (error) {
      console.error("Failed to fetch leaderboard:", error);
      renderLeaderboard([]);
      setSocketStatus("Initial load failed", "offline");
   }

   connectAdminSocket();
};
