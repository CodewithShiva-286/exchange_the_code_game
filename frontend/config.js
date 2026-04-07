const BASE_URL = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
  ? "http://localhost:8000"
  : "http://169.254.69.170:8000";

const WS_URL = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
  ? "ws://localhost:8000"
  : "ws://169.254.69.170:8000";

window.BASE_URL = BASE_URL;
window.WS_URL = WS_URL;
