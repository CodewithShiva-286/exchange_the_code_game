let currentProblemId = null;
let currentPhase = 'waiting';
let submitted = false;

document.getElementById('brandInfo').textContent = `${SESSION.team_id} | Player ${SESSION.player_slot} (${SESSION.player_name})`;

document.getElementById('logoutBtn').addEventListener('click', () => {
    if(confirm('Leave the game?')) {
        localStorage.removeItem('session');
        window.location.href = 'join.html';
    }
});

const UI = {
    setPhaseText: (text) => document.getElementById('phaseLabel').textContent = text,
    setProblemInfo: (title, desc) => {
        document.getElementById('problemTitle').textContent = title;
        document.getElementById('problemDescription').textContent = desc;
    },
    setParts: (partA, partB) => {
        document.getElementById('partAPrompt').textContent = partA;
        document.getElementById('partBPrompt').textContent = partB;
    },
    showPart: (partId) => {
        document.getElementById('partABlock').style.display = (partId === 'partABlock' || partId === 'both') ? 'block' : 'none';
        document.getElementById('partBBlock').style.display = (partId === 'partBBlock' || partId === 'both') ? 'block' : 'none';
    },
    setPartnerStatus: (online) => {
        const el = document.getElementById('partnerStatus');
        el.textContent = online ? "Partner: Online" : "Partner: Offline";
        el.style.color = online ? "#10b981" : "#ef4444";
    }
};

function sanitizeCode(code, language) {
    code = code.replaceAll("===== START PART B BELOW =====", "");

    if (language === "python") {
        code = code.replaceAll("//", "#");
    }

    return code;
}

const Actions = {
    runCode: () => {
        console.log("RUN CLICKED");
        let code = EditorWrap.getValue();
        const lang = document.getElementById('languageSelect').value;
        if(!code || !currentProblemId) {
            console.warn("RUN aborted: code or currentProblemId is missing. problemId:", currentProblemId);
            return;
        }

        // Sanitize code before sending
        code = sanitizeCode(code, lang);

        ResultManager.clear();
        ResultManager.append(`<span style="color:#60a5fa;">Running code...</span>`);
        wsSend("RUN_CODE", { code: code, language: lang, problem_id: currentProblemId });
    },
    submitCode: () => {
        if (submitted) return;
        const confirmSub = confirm(`Are you sure you want to submit?`);
        if (!confirmSub) return;
        actuallySubmitCode();
    }
};

function actuallySubmitCode() {
    let code = EditorWrap.getValue();
    if(!code || !currentProblemId) return;

    // Sanitize code
    const lang = document.getElementById('languageSelect').value;
    code = sanitizeCode(code, lang);

    submitted = true;
    document.getElementById('submitBtn').disabled = true;
    document.getElementById('runBtn').disabled = true;
    EditorWrap.setReadOnly(true);
    ResultManager.append(`<br><span style="color:#10b981;">Code lock and submit requested.</span>`);
    wsSend("FINAL_SUBMIT", { problem_id: currentProblemId, code: code });
}

document.getElementById('runBtn').addEventListener('click', Actions.runCode);
document.getElementById('submitBtn').addEventListener('click', Actions.submitCode);

function HandleWSEvent(msg) {
    console.log("WS Event", msg);
    const { event, data } = msg;

    switch(event) {
        case "CONNECTED":
            ResultManager.append(`<div class="status-info" style="color:#60a5fa;">Connected to server.</div>`);
            break;
        case "PARTNER_JOINED":
            UI.setPartnerStatus(true);
            break;
        case "ASSIGNED":
            currentProblemId = data.assigned_problem.id;
            UI.setProblemInfo(data.assigned_problem.title, data.assigned_problem.description);
            UI.setParts(data.assigned_problem.part_a_prompt, data.partner_problem_title + " (Partner's question details arriving in Part B)");
            document.getElementById('partBadge').textContent = `Assigned (P${data.player_slot || SESSION.player_slot})`;
            if (data.partner_problem_title) {
                document.getElementById('partBPrompt').textContent = `This will integrate with: ${data.partner_problem_title}`;
            }
            break;
        case "START_PART_A":
            currentPhase = 'part_a';
            submitted = false;
            UI.setPhaseText("Part A");
            UI.showPart("partABlock");
            EditorWrap.setReadOnly(false);
            document.getElementById('runBtn').disabled = false;
            document.getElementById('submitBtn').disabled = false;
            
            const draft = StorageManager.getDraft(currentProblemId);
            if (draft && (!EditorWrap.getValue() || EditorWrap.getValue().includes('Waiting'))) {
                EditorWrap.setValue(draft);
            } else if (!EditorWrap.getValue() || EditorWrap.getValue().includes('Waiting')) {
                EditorWrap.setValue("// Start Part A here\n");
            }
            StorageManager.startDrafting(currentProblemId);
            break;
        case "TIMER_TICK":
            TimerUI.update(data.remaining_seconds);
            break;
        case "LOCK_AND_SUBMIT":
            if (!submitted && (currentPhase === 'part_a' || currentPhase === 'part_b')) {
                actuallySubmitCode();
            }
            break;
        case "WAIT_FOR_SWAP":
            currentPhase = 'wait_swap';
            UI.setPhaseText("Waiting for Swap...");
            EditorWrap.setReadOnly(true);
            StorageManager.stopDrafting();
            break;
        case "START_PART_B":
            console.log("START_PART_B EVENT:", data);
            currentPhase = 'part_b';
            submitted = false;
            UI.setPhaseText("Part B");
            
            // Set Part B full problem data
            if (data.full_problem && data.full_problem.id) {
                currentProblemId = data.full_problem.id;
                UI.setProblemInfo(data.full_problem.title, data.full_problem.description);
                UI.setParts(data.full_problem.part_a_prompt, data.part_b_prompt || "Complete Part B!");
            } else {
                document.getElementById('partBPrompt').textContent = data.part_b_prompt || "Complete Part B!";
            }
            
            UI.showPart("both");
            
            // Partner code
            const oldVal = data.partner_code || "// No code received from partner :(";
            EditorWrap.setValue(oldVal + "\n\n// ===== START PART B BELOW =====\n\n");
            
            EditorWrap.setReadOnly(false);
            document.getElementById('runBtn').disabled = false;
            document.getElementById('submitBtn').disabled = false;
            StorageManager.startDrafting(currentProblemId);
            break;
        case "END_GAME":
            currentPhase = 'ended';
            UI.setPhaseText("Game Ended - Evaluating...");
            EditorWrap.setReadOnly(true);
            document.getElementById('runBtn').disabled = true;
            document.getElementById('submitBtn').disabled = true;
            StorageManager.stopDrafting();
            break;
        case "RUN_OUTPUT":
            ResultManager.showRunOutput(data);
            break;
        case "RESULT":
            currentPhase = 'ended';
            UI.setPhaseText("Game Completed");
            TimerUI.clear();
            ResultManager.showFinalResult(data);
            break;
        case "ERROR":
            ResultManager.append(`<div style="color:#ef4444; margin-top:5px;"><strong>Server Error:</strong> ${data.message}</div>`);
            break;
        case "SESSION_RESTORE":
            if (data.assigned_problem) {
                currentProblemId = data.assigned_problem.id;
                UI.setProblemInfo(data.assigned_problem.title, data.assigned_problem.description);
                UI.setParts(data.assigned_problem.part_a_prompt, data.assigned_problem.part_b_prompt);
            }
            if (data.partner && data.partner.connection_status === 'online') {
                UI.setPartnerStatus(true);
            } else {
                UI.setPartnerStatus(false);
            }
            
            if (data.phase) {
                currentPhase = data.phase;
                if (currentPhase === 'waiting' || currentPhase === 'assigned') {
                     UI.setPhaseText("Waiting to Start");
                } else {
                     UI.setPhaseText(currentPhase);
                }
                
                if (currentPhase === 'part_a' || currentPhase === 'part_b') {
                    UI.showPart(currentPhase === 'part_a' ? "partABlock" : "both");
                    EditorWrap.setReadOnly(false);
                    document.getElementById('runBtn').disabled = false;
                    document.getElementById('submitBtn').disabled = false;
                } else if (currentPhase === 'wait_swap' || currentPhase.includes('eval') || currentPhase === 'ended') {
                    EditorWrap.setReadOnly(true);
                    document.getElementById('runBtn').disabled = true;
                    document.getElementById('submitBtn').disabled = true;
                }
            }
            break;
    }
}
