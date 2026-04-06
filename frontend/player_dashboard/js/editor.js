let editor = null;

window.addEventListener('load', () => {
    if (typeof require !== 'undefined') {
        require(['vs/editor/editor.main'], function() {
            editor = monaco.editor.create(document.getElementById('editor-container'), {
                value: "// Waiting for assignment...",
                language: 'python',
                theme: 'vs-dark',
                automaticLayout: true,
                fontSize: 16,
                readOnly: true,
                minimap: { enabled: false }
            });
            window.dispatchEvent(new Event('editorReady'));
        });
    }
});

const EditorWrap = {
    getValue: () => editor ? editor.getValue() : '',
    setValue: (val) => { if (editor) editor.setValue(val); },
    setLanguage: (lang) => { if (editor) monaco.editor.setModelLanguage(editor.getModel(), lang); },
    setReadOnly: (flag) => { 
        if (editor) {
            editor.updateOptions({ readOnly: flag }); 
            const statusEl = document.getElementById('editorStatus');
            if(statusEl) {
                statusEl.textContent = flag ? "Locked (Read-Only)" : "Ready to code";
                statusEl.style.color = flag ? "#ef4444" : "#10b981";
            }
        }
    }
};

const langSel = document.getElementById('languageSelect');
if(langSel) {
    langSel.addEventListener('change', (e) => {
        EditorWrap.setLanguage(e.target.value);
    });
}
