const API_BASE = window.location.origin;

const joinForm = document.getElementById('joinForm');
const teamIdInput = document.getElementById('teamIdInput');
const playerNameInput = document.getElementById('playerNameInput');
const joinBtn = document.getElementById('joinBtn');
const statusArea = document.getElementById('statusArea');

(function checkSession() {
    const session = localStorage.getItem('session');
    if (session) {
        try {
            const data = JSON.parse(session);
            if (data.session_token && data.team_id) {
                window.location.href = 'index.html';
            }
        } catch(e) {
            localStorage.removeItem('session');
        }
    }
})();

function showStatus(msg, type) {
    statusArea.textContent = msg;
    statusArea.className = `status-area ${type}`;
}

joinForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const teamId = teamIdInput.value.trim();
    const name = playerNameInput.value.trim();
    
    if (!teamId || !name) return;

    joinBtn.disabled = true;
    showStatus('Joining...', 'info');

    try {
        const res = await fetch(`${API_BASE}/join`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ team_id: teamId, name: name })
        });
        
        const data = await res.json();
        
        if (!res.ok) {
            showStatus(`Error: ${data.detail || 'Failed to join'}`, 'error');
            joinBtn.disabled = false;
            return;
        }

        const sessionData = {
            team_id: data.team_id,
            player_id: data.player_id,
            session_token: data.session_token,
            player_slot: data.player_slot,
            player_name: name
        };
        
        // Clear old draft code strings to prevent persisting old code across games
        Object.keys(localStorage).forEach(key => {
            if (key.startsWith('draft_')) {
                localStorage.removeItem(key);
            }
        });
        
        localStorage.setItem('session', JSON.stringify(sessionData));
        showStatus(`Joined as P${data.player_slot}! Redirecting...`, 'success');
        
        setTimeout(() => {
            window.location.href = 'index.html';
        }, 1000);
        
    } catch (err) {
        showStatus('Connection error.', 'error');
        joinBtn.disabled = false;
    }
});
