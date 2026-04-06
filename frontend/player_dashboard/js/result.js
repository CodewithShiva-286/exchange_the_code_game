const consoleBox = document.getElementById('consoleBox');

const ResultManager = {
    clear: () => {
        if(consoleBox) consoleBox.innerHTML = '';
    },
    append: (htmlStr) => {
        if(consoleBox) {
            consoleBox.insertAdjacentHTML('beforeend', htmlStr);
            consoleBox.scrollTop = consoleBox.scrollHeight;
        }
    },
    showRunOutput: (outputData) => {
        ResultManager.clear();
        let html = `<h3>Run Results</h3>`;
        if (outputData.error) {
            html += `<div class="console-output status-fail"><strong>Error:</strong><pre>${outputData.error}</pre></div>`;
            if (outputData.output) {
                html += `<div><strong>Output:</strong><pre>${outputData.output}</pre></div>`;
            }
        } else {
            if (outputData.results && outputData.results.length > 0) {
                outputData.results.forEach((tc, idx) => {
                    const statusClass = tc.passed ? 'status-pass' : 'status-fail';
                    const statusText = tc.passed ? 'PASS' : 'FAIL';
                    html += `
                        <div class="console-output">
                            <strong class="${statusClass}">Test ${idx + 1}: ${statusText}</strong>
                            <div><strong>Input:</strong> <pre>${tc.input}</pre></div>
                            <div><strong>Output:</strong> <pre>${tc.actual}</pre></div>
                            <div><strong>Expected:</strong> <pre>${tc.expected}</pre></div>
                        </div>
                    `;
                });
            } else {
                html += `<div class="console-output"><pre>${outputData.output || "Completed successfully"}</pre></div>`;
            }
        }
        ResultManager.append(html);
    },
    showFinalResult: (resultData) => {
        ResultManager.clear();
        let html = `<div class="result-score">Final Score: ${resultData.score || 0}</div>`;
        html += `<p>Passed ${resultData.passed_cases || 0} out of ${resultData.total_cases || 0} test cases.</p>`;
        if (resultData.results) {
            resultData.results.forEach((tc, idx) => {
                const statusClass = tc.passed ? 'status-pass' : 'status-fail';
                const statusText = tc.passed ? 'PASS' : 'FAIL';
                html += `<div class="console-output"><strong class="${statusClass}">Hidden Test ${idx+1}: ${statusText}</strong></div>`;
            });
        }
        ResultManager.append(html);
    }
};

document.getElementById('clearConsoleBtn')?.addEventListener('click', () => {
    ResultManager.clear();
});
