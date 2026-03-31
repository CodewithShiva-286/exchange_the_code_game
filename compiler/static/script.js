// Fetch UI Elements
const runBtn = document.querySelector('.run-btn');
const submitBtn = document.querySelector('.submit-btn');
const switchBtn = document.querySelector('.switch-btn');
const consoleBox = document.querySelector('.console-box');

let currentPhase = 'A';

// 1. Run Button Logic
runBtn.addEventListener('click', () => {

    // Get the current code from Monaco Editor
    const code = editor.getValue();             // --> Variable for getting code text from editor
    console.log("Running Code:", code);
    
    // Placeholder UI update
    consoleBox.innerHTML = '<span style="color: #60a5fa;">Running...</span>';
    
    // Simulate backend execution delay
    setTimeout(() => {
        consoleBox.innerHTML = 'Execution finished. (Backend connection pending)';
    }, 1000);
});

// 2. Submit Button Logic
submitBtn.addEventListener('click', () => {
    const code = editor.getValue();
    console.log("Submitting Code:", code);
    
    // Placeholder UI update
    const confirmSubmit = confirm("Are you sure you want to lock and submit Part A?");
    if(confirmSubmit) {
        editor.updateOptions({ readOnly: true });
        consoleBox.innerHTML = '<span style="color: #16a34a;">Code Submitted Successfully! (Waiting for swap)</span>';
        
    }
});

// 3. Switch Code Button Logic
switchBtn.addEventListener('click', () => {
    console.log("Switching Code...");
    
    consoleBox.innerHTML = '<span style="color: #fbbf24;">Switching to Part B...</span>';
    
    setTimeout(() => {

        // 🔁 Reset time
        timeRemaining = 90;

        editor.updateOptions({ readOnly: false });
        editor.setValue("// Partner's Part A...\n\n// Continue Part B here:\n");
        document.getElementById('phaseLabel').innerText = "Part B";
        document.getElementById('partBadge').innerText = "PART B";
        consoleBox.innerHTML = 'Ready to code Part B.';

        // ▶️ Start new timer
        startTimer();

        // Existing logic
        
    }, 1500);
});

// 4. Timer Logic
const timerElement = document.getElementById('timer');
let timeRemaining = 90; // 3 minutes (180 seconds)
let timerInterval = null;
function formatTime(seconds) {
    const m = Math.floor(seconds / 60).toString().padStart(2, '0');
    const s = (seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
}

// Timer function for 
function startTimer() {
    clearInterval(timerInterval);

    timerInterval = setInterval(() => {

        if (timeRemaining <= 0) {
            clearInterval(timerInterval);
            timerElement.innerText = "00:00";

            if (currentPhase === "A") {
                // 🔥 AUTO SWITCH TO PART B
                switchToPartB(true);
            } else {
                // ⛔ End of Part B → lock editor
                editor.updateOptions({ readOnly: true });
                consoleBox.innerHTML = '<span style="color: #ef4444;">Final Time Over! Code locked.</span>';
            }

        } else {
            timerElement.innerText = formatTime(timeRemaining);
            timeRemaining--;
        }

    }, 1000);
}
window.onload = () => {
    timeRemaining = 90;
    startTimer();
};

const dragBar = document.getElementById("drag-bar");
const editorContainer = document.getElementById("editor-container");
const consolePanel = document.querySelector(".bottom-panel");

let isDragging = false;

dragBar.addEventListener("mousedown", () => {
  isDragging = true;
  document.body.style.cursor = "row-resize";
});

document.addEventListener("mousemove", (e) => {
  if (!isDragging) return;

  const containerTop = editorContainer.parentElement.getBoundingClientRect().top;
  const totalHeight = editorContainer.parentElement.clientHeight;

  let newEditorHeight = e.clientY - containerTop;

  // Limits (important)
  if (newEditorHeight < 150) newEditorHeight = 150;
  if (newEditorHeight > totalHeight - 100) newEditorHeight = totalHeight - 100;

  editorContainer.style.height = `${newEditorHeight}px`;
  consolePanel.style.height = `${totalHeight - newEditorHeight - 6}px`;

  // 🔥 VERY IMPORTANT for Monaco
  if (editor) {
    editor.layout();
  }
});

document.addEventListener("mouseup", () => {
  isDragging = false;
  document.body.style.cursor = "default";
});

// Function for switching the part A and part B logic

switchBtn.addEventListener('click', () => {
    switchToPartB(false);
});

function switchToPartB(auto = false) {
    if (currentPhase === "B") return; // prevent double switch

    currentPhase = "B";

    console.log("Switching to Part B...");

    consoleBox.innerHTML = auto
        ? '<span style="color: #f97316;">Auto-switching to Part B...</span>'
        : '<span style="color: #fbbf24;">Switching to Part B...</span>';

    setTimeout(() => {

        // 🔁 Reset timer for Part B
        timeRemaining = 90;

        // 🔓 Unlock editor
        editor.updateOptions({ readOnly: false });

        // 🔁 Load partner code (placeholder)
        editor.setValue("// Partner's Part A...\n\n// Continue Part B here:\n");

        // 🧠 Update UI
        document.getElementById('phaseLabel').innerText = "Part B";
        document.getElementById('partBadge').innerText = "PART B";

        // 👇 Toggle visibility
        document.getElementById("partA-block").style.display = "none";
        document.getElementById("partB-block").style.display = "block";

        consoleBox.innerHTML = 'Ready to code Part B.';

        // ▶️ Restart timer
        startTimer();

    }, 1200);
}