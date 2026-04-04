// Problem groups (future: fetch from backend)
const problemGroups = {
   G1: ["Array Basics", "Binary Search"],
   G2: ["Graphs", "DFS/BFS"],
   G3: ["Dynamic Programming", "Knapsack"],
   G4: ["Strings", "Pattern Matching"],
   G5: ["Greedy", "Intervals"]
};

const teams = 10;

// Render table
function renderTable() {
   const table = document.getElementById("assignmentTable");
   table.innerHTML = "";

   for (let i = 1; i <= teams; i++) {
      const row = document.createElement("tr");

      row.innerHTML = `
            <td>Team ${i}</td>

            <td>
                <select onchange="updateProblems(${i}, this.value)">
                    <option value="">Select Group</option>
                    ${Object.keys(problemGroups).map(g => `<option value="${g}">${g}</option>`).join("")}
                </select>
            </td>

            <td id="p1-${i}">-</td>
            <td id="p2-${i}">-</td>
        `;

      table.appendChild(row);
   }
}

// Update problems based on group
function updateProblems(teamId, groupId) {
   if (!groupId) return;

   const [p1, p2] = problemGroups[groupId];

   document.getElementById(`p1-${teamId}`).innerText = p1;
   document.getElementById(`p2-${teamId}`).innerText = p2;
}

// Save assignments (future: send to backend)
document.getElementById("saveBtn").addEventListener("click", () => {
   let assignments = [];

   for (let i = 1; i <= teams; i++) {
      const p1 = document.getElementById(`p1-${i}`).innerText;
      const p2 = document.getElementById(`p2-${i}`).innerText;

      assignments.push({
         team: `Team ${i}`,
         problem1: p1,
         problem2: p2
      });
   }

   console.log("Saved Assignments:", assignments);

   // Optional: store locally
   localStorage.setItem("assignments", JSON.stringify(assignments));

   alert("Assignments Saved ✅");
});

// Back button
document.getElementById("backBtn").addEventListener("click", () => {
   window.location.href = "index.html";
});

// init
renderTable();