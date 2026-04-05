// ══════════════════════════════════════════════════════════════════════════════
// Exchange Code Game — Frontend Logic
// ══════════════════════════════════════════════════════════════════════════════

const API_BASE = 'http://localhost:8000';

// ── UI Element References ────────────────────────────────────────────────────
const runBtn      = document.getElementById('runBtn');
const submitBtn   = document.getElementById('submitBtn');
const switchBtn   = document.getElementById('switchBtn');
const consoleBox  = document.querySelector('.console-box');
const timerElement = document.getElementById('timer');
const phaseLabel  = document.getElementById('phaseLabel');
const partBadge   = document.getElementById('partBadge');

// Problem panel elements
const problemSelect      = document.getElementById('problemSelect');
const problemTitle       = document.getElementById('problem-title');
const problemDescription = document.getElementById('problem-description');
const partAEl            = document.getElementById('partA');
const partBEl            = document.getElementById('partB');
const loadingOverlay     = document.getElementById('problemLoading');

// Drag bar elements
const dragBar          = document.getElementById('drag-bar');
const editorContainer  = document.getElementById('editor-container');
const consolePanel     = document.querySelector('.bottom-panel');

// ── Game State ───────────────────────────────────────────────────────────────
let currentPhase   = 'A';           // 'A' or 'B'
let timeRemaining  = 10;            // seconds (testing)
let timerInterval  = null;
let timerExpired   = false;         // True once Part A timer hits 0
let codeSubmitted  = false;         // True after Part A code submitted to backend
let switchDone     = false;         // True after switch has been performed
let retryInterval  = null;          // For auto-retrying partner code fetch

// ── Session Data (from /join via localStorage) ───────────────────────────────
const sessionRaw = localStorage.getItem('session');
const SESSION    = sessionRaw ? JSON.parse(sessionRaw) : null;
const TEAM_ID    = SESSION ? SESSION.team_id : '';
const PLAYER     = SESSION ? SESSION.player : 'A';       // 'A' or 'B'
const PLAYER_NAME = SESSION ? SESSION.player_name : '';

// Display team/player info in topbar
const brandInfo = document.getElementById('brandInfo');
if (brandInfo && SESSION) {
    brandInfo.textContent = `${TEAM_ID} | Player ${PLAYER} (${PLAYER_NAME})`;
}

// ── Logout Button ────────────────────────────────────────────────────────────
const logoutBtn = document.getElementById('logoutBtn');
if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
        if (confirm('Leave the game? Your session will be cleared.')) {
            localStorage.removeItem('session');
            window.location.href = 'join.html';
        }
    });
}

// ══════════════════════════════════════════════════════════════════════════════
// 1. RUN BUTTON
// ══════════════════════════════════════════════════════════════════════════════
runBtn.addEventListener('click', async () => {
    const code     = editor.getValue();
    const language = document.querySelector('.language-select').value.toLowerCase();

    consoleBox.innerHTML = '<span style="color: #60a5fa;">Compiling and Running...</span>';

    try {
        const response = await fetch(`${API_BASE}/run-code`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, language }),
        });

        const result = await response.json();

        if (result.error) {
            consoleBox.innerHTML = `<pre style="color: #ef4444;">${result.error}</pre>`;
        } else {
            consoleBox.innerHTML = `<pre style="color: #f8fafc;">${result.output}</pre>`;
        }
    } catch (err) {
        consoleBox.innerHTML = '<span style="color: #ef4444;">Connection Error: Is the FastAPI server running?</span>';
    }
});

// ══════════════════════════════════════════════════════════════════════════════
// 2. SUBMIT BUTTON — Sends Part A code to backend
// ══════════════════════════════════════════════════════════════════════════════
submitBtn.addEventListener('click', async () => {
    if (codeSubmitted && currentPhase === 'A') {
        consoleBox.innerHTML = '<span style="color: #fbbf24;">Part A code already submitted.</span>';
        return;
    }

    const code = editor.getValue();
    const confirmSubmit = confirm(
        currentPhase === 'A'
            ? "Are you sure you want to lock and submit Part A?"
            : "Are you sure you want to submit your final Part B solution?"
    );

    if (!confirmSubmit) return;

    const problemId = problemSelect.value;

    consoleBox.innerHTML = '<span style="color: #60a5fa;">Submitting code...</span>';

    try {
        const response = await fetch(`${API_BASE}/submit-code`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                team_id: TEAM_ID,
                player: PLAYER,
                problem_id: problemId,
                code: code,
            }),
        });

        const result = await response.json();

        if (result.status === 'success') {
            if (currentPhase === 'A') {
                codeSubmitted = true;
                editor.updateOptions({ readOnly: true });
                consoleBox.innerHTML = '<span style="color: #16a34a;">✓ Part A submitted! Waiting for timer to end for code exchange.</span>';

                // If timer already expired, enable switch immediately
                if (timerExpired) {
                    enableSwitchButton();
                }
            } else {
                editor.updateOptions({ readOnly: true });
                consoleBox.innerHTML = '<span style="color: #16a34a;">✓ Part B submitted! Final solution locked.</span>';
                submitBtn.disabled = true;
            }
        } else {
            consoleBox.innerHTML = `<span style="color: #ef4444;">Submit failed: ${result.message || 'Unknown error'}</span>`;
        }
    } catch (err) {
        consoleBox.innerHTML = '<span style="color: #ef4444;">Connection Error: Could not submit code.</span>';
    }
});

// ══════════════════════════════════════════════════════════════════════════════
// 3. SWITCH CODE — Fetches partner code from backend (only after timer ends)
// ══════════════════════════════════════════════════════════════════════════════
switchBtn.addEventListener('click', async () => {
    if (!timerExpired) {
        consoleBox.innerHTML = '<span style="color: #ef4444;">Cannot switch yet — timer is still running.</span>';
        return;
    }

    if (switchDone) {
        consoleBox.innerHTML = '<span style="color: #fbbf24;">Code already switched.</span>';
        return;
    }

    // Disable button during fetch
    switchBtn.disabled = true;
    switchBtn.classList.remove('pulse');

    consoleBox.innerHTML = '<span style="color: #60a5fa;">Fetching partner\'s code...</span>';

    await fetchPartnerCode();
});

async function fetchPartnerCode() {
    const problemId = problemSelect.value;

    try {
        const url = `${API_BASE}/get-partner-code?team_id=${TEAM_ID}&problem_id=${problemId}&player=${PLAYER}`;
        const response = await fetch(url);
        const result = await response.json();

        if (result.status === 'success' && result.code) {
            // ── SUCCESS: Got partner's code ──────────────────────────────
            clearRetryInterval();
            switchDone = true;
            currentPhase = 'B';

            // Set editor to partner's code + separator
            editor.setValue(
                result.code +
                "\n\n// ===== Continue Part B Below =====\n\n"
            );
            editor.updateOptions({ readOnly: false });

            // Update UI labels
            phaseLabel.innerText = "Part B";
            partBadge.innerText = "PART B";

            // Show Part B question
            document.getElementById("partB-block").style.display = "block";
            document.getElementById("partB-block").scrollIntoView({ behavior: "smooth" });

            // Reset and start Part B timer
            timeRemaining = 10;
            startTimer();

            // Re-enable submit for Part B, disable switch
            submitBtn.disabled = false;
            switchBtn.disabled = true;

            consoleBox.innerHTML = '<span style="color: #16a34a;">✓ Partner\'s code loaded. Start coding Part B!</span>';

        } else {
            // ── WAITING: Partner hasn't submitted yet ────────────────────
            showWaitingState();
            startRetryPolling();
        }
    } catch (err) {
        consoleBox.innerHTML = `
            <span style="color: #ef4444;">Error fetching partner code. </span>
            <button onclick="retryFetchPartnerCode()" style="
                background: #7c3aed; color: white; border: none; padding: 6px 14px;
                border-radius: 6px; cursor: pointer; margin-left: 8px; font-weight: bold;
            ">Retry</button>
        `;
        switchBtn.disabled = false;
    }
}

function showWaitingState() {
    consoleBox.innerHTML = `
        <div class="waiting-indicator">
            <span class="dot-pulse">●</span>
            <span>Waiting for partner to submit code... (auto-retrying every 3s)</span>
            <button onclick="cancelRetry()" style="
                background: #475569; color: white; border: none; padding: 4px 10px;
                border-radius: 6px; cursor: pointer; font-size: 12px; margin-left: auto;
            ">Cancel</button>
        </div>
    `;
}

function startRetryPolling() {
    clearRetryInterval();
    retryInterval = setInterval(async () => {
        await fetchPartnerCode();
    }, 3000);
}

function clearRetryInterval() {
    if (retryInterval) {
        clearInterval(retryInterval);
        retryInterval = null;
    }
}

// Global functions for inline onclick handlers
window.retryFetchPartnerCode = function () {
    fetchPartnerCode();
};

window.cancelRetry = function () {
    clearRetryInterval();
    switchBtn.disabled = false;
    switchBtn.classList.add('pulse');
    consoleBox.innerHTML = '<span style="color: #fbbf24;">Retry cancelled. Click "Switch Code" to try again.</span>';
};

// ══════════════════════════════════════════════════════════════════════════════
// 4. TIMER LOGIC
// ══════════════════════════════════════════════════════════════════════════════
function formatTime(seconds) {
    const m = Math.floor(seconds / 60).toString().padStart(2, '0');
    const s = (seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
}

function startTimer() {
    clearInterval(timerInterval);

    timerInterval = setInterval(() => {
        if (timeRemaining <= 0) {
            clearInterval(timerInterval);
            timerElement.innerText = "00:00";

            if (currentPhase === 'A') {
                // ── Part A timer expired ─────────────────────────────────
                timerExpired = true;
                editor.updateOptions({ readOnly: true });

                if (codeSubmitted) {
                    // Code already submitted → enable switch
                    enableSwitchButton();
                    consoleBox.innerHTML = '<span style="color: #fbbf24;">⏰ Time\'s up! Click "Switch Code" to receive your partner\'s code.</span>';
                } else {
                    // Auto-submit the code
                    consoleBox.innerHTML = '<span style="color: #ef4444;">⏰ Time\'s up! Auto-submitting your code...</span>';
                    autoSubmitPartA();
                }
            } else {
                // ── Part B timer expired ─────────────────────────────────
                editor.updateOptions({ readOnly: true });
                consoleBox.innerHTML = '<span style="color: #ef4444;">⏰ Part B time is up! Code locked.</span>';
            }
        } else {
            timerElement.innerText = formatTime(timeRemaining);
            timeRemaining--;
        }
    }, 1000);
}

function enableSwitchButton() {
    switchBtn.disabled = false;
    switchBtn.classList.add('pulse');
}

async function autoSubmitPartA() {
    const code = editor.getValue();
    const problemId = problemSelect.value;

    try {
        const response = await fetch(`${API_BASE}/submit-code`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                team_id: TEAM_ID,
                player: PLAYER,
                problem_id: problemId,
                code: code,
            }),
        });

        const result = await response.json();

        if (result.status === 'success') {
            codeSubmitted = true;
            enableSwitchButton();
            consoleBox.innerHTML = '<span style="color: #fbbf24;">⏰ Time\'s up! Code auto-submitted. Click "Switch Code" to continue.</span>';
        } else {
            consoleBox.innerHTML = '<span style="color: #ef4444;">Auto-submit failed. Please try submitting manually.</span>';
        }
    } catch (err) {
        consoleBox.innerHTML = '<span style="color: #ef4444;">Connection error during auto-submit.</span>';
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// 5. PROBLEM FETCHING
// ══════════════════════════════════════════════════════════════════════════════
async function loadProblem(problemId) {
    loadingOverlay.classList.add('visible');
    document.getElementById("partB-block").style.display = "none";
    phaseLabel.innerText = "Part A";
    partBadge.innerText = "PART A";

    try {
        const response = await fetch(`${API_BASE}/problem/${problemId}`);
        if (!response.ok) {
            throw new Error(`Problem not found (${response.status})`);
        }

        const data = await response.json();

        problemTitle.innerText       = data.title;
        problemDescription.innerText = data.description;
        partAEl.innerText            = data.part_a_prompt;
        partBEl.innerText            = data.part_b_prompt;

        // Fade-in animation
        [problemTitle, problemDescription, partAEl, partBEl].forEach(el => {
            el.classList.remove('fade-in');
            void el.offsetWidth;
            el.classList.add('fade-in');
        });

    } catch (err) {
        problemTitle.innerText       = 'Error loading problem';
        problemDescription.innerText = err.message || 'Could not connect to the server.';
        partAEl.innerText            = '—';
        partBEl.innerText            = '—';
    } finally {
        loadingOverlay.classList.remove('visible');
    }
}

problemSelect.addEventListener('change', () => {
    loadProblem(problemSelect.value);
});

// ══════════════════════════════════════════════════════════════════════════════
// 6. DRAG BAR (editor / console resize)
// ══════════════════════════════════════════════════════════════════════════════
let isDragging = false;

dragBar.addEventListener('mousedown', () => {
    isDragging = true;
    document.body.style.cursor = 'row-resize';
});

document.addEventListener('mousemove', (e) => {
    if (!isDragging) return;

    const containerTop = editorContainer.parentElement.getBoundingClientRect().top;
    const totalHeight  = editorContainer.parentElement.clientHeight;

    let newEditorHeight = e.clientY - containerTop;
    if (newEditorHeight < 150) newEditorHeight = 150;
    if (newEditorHeight > totalHeight - 100) newEditorHeight = totalHeight - 100;

    editorContainer.style.height = `${newEditorHeight}px`;
    consolePanel.style.height    = `${totalHeight - newEditorHeight - 6}px`;

    if (editor) editor.layout();
});

document.addEventListener('mouseup', () => {
    isDragging = false;
    document.body.style.cursor = 'default';
});

// ══════════════════════════════════════════════════════════════════════════════
// 7. PAGE INIT
// ══════════════════════════════════════════════════════════════════════════════
window.onload = () => {
    // Ensure switch is disabled on load
    switchBtn.disabled = true;
    switchBtn.classList.remove('pulse');

    // Reset state
    currentPhase  = 'A';
    timerExpired  = false;
    codeSubmitted = false;
    switchDone    = false;
    timeRemaining = 10;

    startTimer();
    loadProblem(problemSelect.value);
};