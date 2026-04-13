const TimerText = document.getElementById('timer');

const TimerUI = {
    update: (timeRemaining) => {
        if (!TimerText) return;
        const m = Math.floor(timeRemaining / 60).toString().padStart(2, '0');
        const s = (timeRemaining % 60).toString().padStart(2, '0');
        TimerText.textContent = `${m}:${s}`;
    },
    clear: () => {
        if (TimerText) TimerText.textContent = "--:--";
    }
};
