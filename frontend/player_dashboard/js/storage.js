const sessionRaw = localStorage.getItem('session');
if (!sessionRaw) {
    window.location.href = 'join.html';
}

const SESSION = JSON.parse(sessionRaw);
let draftInterval = null;

const StorageManager = {
    startDrafting: (problem_id) => {
        if (draftInterval) clearInterval(draftInterval);
        draftInterval = setInterval(() => {
            const code = EditorWrap.getValue();
            if (code && typeof wsSend === 'function') {
                wsSend("DRAFT_SAVE", { problem_id: problem_id, code: code });
            }
            localStorage.setItem(`draft_${SESSION.team_id}_${problem_id}`, code);
        }, 10000);
    },
    stopDrafting: () => {
        if (draftInterval) {
            clearInterval(draftInterval);
            draftInterval = null;
        }
    },
    getDraft: (problem_id) => {
        return localStorage.getItem(`draft_${SESSION.team_id}_${problem_id}`);
    }
};
