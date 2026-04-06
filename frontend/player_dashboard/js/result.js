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
        console.log("RUN_OUTPUT RECEIVED:", outputData);
        ResultManager.clear();
        let html = `<h3>Run Results</h3>`;
        
        if (outputData.error_message || outputData.status === 'runtime_error' || outputData.status === 'compile_error' || outputData.status === 'timeout') {
            const errText = outputData.error_message || outputData.stderr || "Execution Failed";
            html += `<div class="console-output status-fail" style="margin-bottom: 10px;">
                        <strong>Error (${outputData.status || 'runtime'}):</strong>
                        <pre style="white-space: pre-wrap; font-family: monospace; overflow-x: auto;">${errText}</pre>
                     </div>`;
        }
        
        if (outputData.stdout && String(outputData.stdout).trim() !== "") {
            html += `<div class="console-output" style="margin-bottom: 10px;">
                        <strong>Program Output:</strong>
                        <pre style="white-space: pre-wrap; font-family: monospace; overflow-x: auto;">${outputData.stdout}</pre>
                     </div>`;
        }

        if (outputData.test_results && outputData.test_results.length > 0) {
            outputData.test_results.forEach((tc, idx) => {
                const statusClass = tc.passed ? 'status-pass' : 'status-fail';
                const statusText = tc.passed ? 'PASS' : 'FAIL';
                
                let testHtml = `
                    <div class="console-output" style="margin-bottom: 10px;">
                        <strong class="${statusClass}">Test ${idx + 1}: ${statusText}</strong>
                        <div><strong>Input:</strong> <pre>${tc.input_data || 'None'}</pre></div>
                        <div><strong>Output:</strong> <pre>${tc.actual_output || 'None'}</pre></div>
                        <div><strong>Expected:</strong> <pre>${tc.expected_output || 'None'}</pre></div>
                `;
                
                if (tc.error) {
                    testHtml += `<div><strong>Test Error:</strong> <pre style="color: #ef4444;">${tc.error}</pre></div>`;
                }
                
                testHtml += `</div>`;
                html += testHtml;
            });
        }
        
        ResultManager.append(html);
    },
    showFinalResult: (resultData) => {
        ResultManager.clear();
        let html = `<div class="result-score">Final Score: ${resultData.score || 0}</div>`;
        html += `<p>Passed ${resultData.passed_count || 0} out of ${resultData.total_test_cases || 0} test cases.</p>`;
        if (resultData.breakdown && resultData.breakdown.length > 0) {
            resultData.breakdown.forEach((tc, idx) => {
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
