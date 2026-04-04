// Sample scores (later replace with real data)
let teams = [
   { name: "Team 1", score: 120 },
   { name: "Team 2", score: 80 },
   { name: "Team 3", score: 150 },
   { name: "Team 4", score: 60 },
   { name: "Team 5", score: 200 },
   { name: "Team 6", score: 90 },
   { name: "Team 7", score: 110 },
   { name: "Team 8", score: 50 },
   { name: "Team 9", score: 70 },
   { name: "Team 10", score: 130 }
];

// Sort and render leaderboard
function renderLeaderboard() {
   teams.sort((a, b) => b.score - a.score);

   const tbody = document.getElementById("leaderboardBody");
   tbody.innerHTML = "";

   teams.forEach((team, index) => {
      const row = document.createElement("tr");

      let rankClass = "";
      if (index === 0) rankClass = "rank-1";
      else if (index === 1) rankClass = "rank-2";
      else if (index === 2) rankClass = "rank-3";

      row.innerHTML = `
            <td class="${rankClass}">${index + 1}</td>
            <td>${team.name}</td>
            <td>${team.score}</td>
        `;

      tbody.appendChild(row);
   });
}

// Back button
document.getElementById("backBtn").addEventListener("click", () => {
   window.location.href = "index.html";
});

renderLeaderboard();
