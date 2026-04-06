let ws = null;
let reconnectTries = 0;
const MAX_RECONNECT = 5;

function connectWS() {
    if (!SESSION || !SESSION.team_id || !SESSION.player_id || !SESSION.session_token) return;
    
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProto}//${window.location.host}/ws/${SESSION.team_id}/${SESSION.player_id}?token=${SESSION.session_token}`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log("WebSocket connected");
        reconnectTries = 0;
    };
    
    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.event === 'PING') {
               wsSend('PONG', {});
            } else {
               HandleWSEvent(msg);
            }
        } catch(e) {
            console.error("Failed to parse WS msg", e);
        }
    };
    
    ws.onclose = (event) => {
        console.log("WebSocket closed", event);
        if (event.code === 4001 || event.code === 4002) {
            // Invalid session or player not found, do not reconnect
            localStorage.removeItem('session');
            window.location.href = 'join.html';
            return;
        }
        
        if (reconnectTries < MAX_RECONNECT) {
            reconnectTries++;
            console.log(`Reconnecting... attempt ${reconnectTries}`);
            setTimeout(connectWS, Math.min(1000 * reconnectTries, 5000));
        } else {
            document.getElementById('phaseLabel').textContent = "Disconnected";
        }
    };
    
    ws.onerror = (error) => {
        console.error("WebSocket error", error);
    };
}

function wsSend(event, data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ event, data }));
    } else {
        console.warn("WebSocket not open, cannot send", event);
    }
}

// Init connection when page loads
window.addEventListener('load', () => {
    connectWS();
});
