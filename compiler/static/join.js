// ══════════════════════════════════════════════════════════════════════════════
// Join Game — Frontend Logic
// ══════════════════════════════════════════════════════════════════════════════

const API_BASE = 'http://localhost:8000';

// ── UI References ────────────────────────────────────────────────────────────
const joinForm       = document.getElementById('joinForm');
const teamIdInput    = document.getElementById('teamIdInput');
const playerNameInput = document.getElementById('playerNameInput');
const joinBtn        = document.getElementById('joinBtn');
const statusArea     = document.getElementById('statusArea');

// ── Check if already logged in ───────────────────────────────────────────────
(function checkExistingSession() {
    const session = localStorage.getItem('session');
    if (session) {
        try {
            const data = JSON.parse(session);
            if (data.session_token && data.team_id) {
                // Already joined — go straight to game
                window.location.href = 'index.html';
                return;
            }
        } catch (e) {
            localStorage.removeItem('session');
        }
    }
})();

// ── Create Background Particles ──────────────────────────────────────────────
(function createParticles() {
    const container = document.getElementById('bgParticles');
    const colors = ['#3b82f6', '#7c3aed', '#f472b6', '#60a5fa', '#a78bfa'];

    for (let i = 0; i < 20; i++) {
        const particle = document.createElement('div');
        particle.classList.add('particle');

        const size = Math.random() * 6 + 3;
        const color = colors[Math.floor(Math.random() * colors.length)];
        const left = Math.random() * 100;
        const duration = Math.random() * 12 + 8;
        const delay = Math.random() * 8;

        particle.style.width = `${size}px`;
        particle.style.height = `${size}px`;
        particle.style.backgroundColor = color;
        particle.style.left = `${left}%`;
        particle.style.animationDuration = `${duration}s`;
        particle.style.animationDelay = `${delay}s`;

        container.appendChild(particle);
    }
})();

// ── Form Submit ──────────────────────────────────────────────────────────────
joinForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const teamId     = teamIdInput.value.trim();
    const playerName = playerNameInput.value.trim();

    // Validation
    if (!teamId) {
        showStatus('Please enter a Team ID.', 'error');
        teamIdInput.focus();
        return;
    }
    if (!playerName) {
        showStatus('Please enter your name.', 'error');
        playerNameInput.focus();
        return;
    }

    // Disable form during request
    setLoading(true);
    showStatus('Joining game...', 'info');

    try {
        const response = await fetch(`${API_BASE}/join`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                team_id: teamId,
                name: playerName,
            }),
        });

        const result = await response.json();

        if (!response.ok) {
            // Handle known errors
            const errorMsg = result.detail || result.message || 'Failed to join team.';
            showStatus(`❌ ${errorMsg}`, 'error');
            setLoading(false);
            return;
        }

        // ── Success ──────────────────────────────────────────────────────
        // Map player_slot (1 or 2) → player identity ('A' or 'B')
        const playerIdentity = result.player_slot === 1 ? 'A' : 'B';

        const sessionData = {
            team_id: result.team_id,
            player_id: result.player_id,
            player_slot: result.player_slot,
            player: playerIdentity,
            session_token: result.session_token,
            player_name: playerName,
        };

        localStorage.setItem('session', JSON.stringify(sessionData));

        showStatus(
            `✅ Joined as Player ${playerIdentity} (Slot ${result.player_slot})! Redirecting...`,
            'success'
        );

        // Short delay for the user to see the success message
        setTimeout(() => {
            window.location.href = 'index.html';
        }, 1000);

    } catch (err) {
        showStatus('❌ Connection error. Is the server running?', 'error');
        setLoading(false);
    }
});

// ── Helpers ──────────────────────────────────────────────────────────────────

function showStatus(message, type) {
    statusArea.textContent = message;
    statusArea.className = `status-area ${type}`;
}

function setLoading(isLoading) {
    joinBtn.disabled = isLoading;
    teamIdInput.disabled = isLoading;
    playerNameInput.disabled = isLoading;

    if (isLoading) {
        joinBtn.classList.add('loading');
        joinBtn.querySelector('.btn-text').textContent = 'Joining...';
    } else {
        joinBtn.classList.remove('loading');
        joinBtn.querySelector('.btn-text').textContent = 'Join Game';
    }
}
