const teams = 10;

// sample problems
const problems = [
   "Array Basics",
   "Binary Search",
   "Graph Traversal",
   "Dynamic Programming",
   "Strings",
   "Greedy"
];

// render teams
function createTeams() {
   const container = document.getElementById("teamContainer");
   container.innerHTML = "";

   for (let i = 1; i <= teams; i++) {
      const card = document.createElement("div");
      card.className = "team-card";

      card.innerHTML = `
            <h3>Team ${i}</h3>

            <div class="status">
                <span class="dot green"></span> P1
                <span class="dot green"></span> P2
            </div>

            <p>Assigned: <b id="assigned-${i}">None</b></p>

            <select onchange="assignProblem(${i}, this.value)">
                <option value="">Assign Problem...</option>
                ${problems.map(p => `<option value="${p}">${p}</option>`).join("")}
            </select>

            <button class="btn-swap" onclick="forceSwap(${i})">Force Swap</button>
        `;

      container.appendChild(card);
   }
}

// assign problem
function assignProblem(teamId, problem) {
   if (!problem) return;

   document.getElementById(`assigned-${teamId}`).innerText = problem;

   console.log(`Team ${teamId} assigned ${problem}`);
}

// force swap
function forceSwap(teamId) {
   alert(`Force Swap triggered for Team ${teamId}`);
}

// start all
function startAll() {
   alert("Competition Started for All Teams 🚀");
}

// reset all
function resetAll() {
   if (confirm("Are you sure you want to reset?")) {
      createTeams();
   }
}

// leaderboard
document.getElementById("leaderboardBtn")
   .addEventListener("click", () => {
      window.location.href = "leaderboard.html";
   });

// manage assignments
document.getElementById("manageBtn")
   .addEventListener("click", () => {
      window.location.href = "manage-assign.html";
   });

// init
createTeams();