// Import dependencies from node_modules locally!
import { Network } from 'vis-network';
import { DataSet } from 'vis-data';
import { marked } from 'marked';

// State Variables (attached to window for HTML access)
window.allNodes = [];
window.network = null;
window.currentSelectedNodeId = null;
window.chatMessageHistory = [];

// Helper functions
function escapeHTML(str) {
    if (!str) return "";
    return str.replace(/[&<>'"]/g, tag => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[tag]));
}

window.toggleModal = function(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.toggle('hidden');
        if (!el.classList.contains('hidden')) window.loadConfig();
    }
}

window.setTab = function(tab) {
    ['structural', 'semantic', 'chat'].forEach(t => {
        document.getElementById(`tab-${t}`).classList.add('hidden');
        let btn = document.getElementById(`btn-${t}`);
        btn.classList.remove('border-cyan-500', 'text-cyan-400');
        btn.classList.add('border-transparent', 'text-slate-400');
    });
    document.getElementById(`tab-${tab}`).classList.remove('hidden');
    let actBtn = document.getElementById(`btn-${tab}`);
    actBtn.classList.add('border-cyan-500', 'text-cyan-400');
    actBtn.classList.remove('border-transparent', 'text-slate-400');
}

// Graph Initialization
async function initGraph() {
    const res = await fetch('/api/graph');
    const data = await res.json();
    window.allNodes = data.nodes;
    
    const container = document.getElementById('network-canvas');
    const options = {
        nodes: { font: { color: '#f8fafc', size: 12, multi: true }, borderWidth: 1 },
        edges: { smooth: { type: 'continuous' } },
        physics: { 
            stabilization: true, 
            barnesHut: { 
                gravitationalConstant: -6000,
                springLength: 250,
                springConstant: 0.01,
                centralGravity: 0.03,
                damping: 0.3,
                avoidOverlap: 0.2
            } 
        }
    };
    
    // Use the imported vis-network objects
    window.network = new Network(container, { 
        nodes: new DataSet(data.nodes), 
        edges: new DataSet(data.edges) 
    }, options);
    
    window.network.on('dragEnd', function(params) {
        if (params.nodes && params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            window.network.body.nodes[nodeId].setOptions({ physics: false }); 
        }
    });

    window.network.on('click', function(params) {
        if (params.nodes.length > 0) {
            const node = window.allNodes.find(n => n.id === params.nodes[0]);
            if (node) {
                window.currentSelectedNodeId = node.id;
                document.getElementById('struct-target').value = node.raw_name;
                document.getElementById('inspector-details').innerHTML = `
                    <h3 class="font-bold text-sm text-cyan-400 mb-1">${node.raw_name}</h3>
                    <div class="flex gap-2 text-xs mb-2">
                        <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 uppercase">${node.kind}</span>
                        <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300">L${node.lines}</span>
                    </div>
                    <p class="mb-2"><b>File:</b> ${node.file}</p>
                    <div class="mt-3 text-slate-400"><b>Docstring:</b>
                        <div class="max-h-24 overflow-y-auto bg-slate-950 p-2 rounded mt-1 border border-border">${escapeHTML(node.docstring)}</div>
                    </div>
                    <div class="mt-3 text-slate-400"><b>Source Code:</b>
                        <pre class="bg-slate-950 p-2 rounded text-[10px] overflow-auto text-emerald-400 mt-1 border border-border max-h-64 scrollbar-thin">${escapeHTML(node.code)}</pre>
                    </div>
                `;
            }
        } else {
            window.currentSelectedNodeId = null;
        }
    });
}

// Core Features
window.runStructural = async function(cmd, forceNodeId = null) {
    const target = document.getElementById('struct-target').value.trim();
    if (!target) return;

    const finalNodeId = forceNodeId || window.currentSelectedNodeId;
    const panel = document.getElementById('inspector-details');
    panel.innerHTML = '<div class="text-slate-500 italic text-center mt-10">Loading...</div>';

    const maxDepth = parseInt(localStorage.getItem('cg_depth') || '2');
    const payload = { command: cmd, target: target, depth: maxDepth };
    if (finalNodeId) payload.node_id = finalNodeId;

    try {
        const res = await fetch('/api/query/structural', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.status === "error") {
            panel.innerHTML = `<div class="text-rose-400 text-sm p-2 bg-rose-950/30 border border-rose-900/50 rounded">${data.message}</div>`;
            return;
        }

        if (data.status === "multiple_matches") {
            let html = `<h3 class="font-bold mb-3 text-rose-300">Multiple matches found for '${target}':</h3><div class="flex flex-col gap-2">`;
            data.data.forEach(n => {
                const safeId = n.id.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                const safeName = n.name.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                
                html += `<div class="p-2 bg-slate-800 hover:bg-slate-700 cursor-pointer rounded text-xs border border-slate-600 transition-colors" 
                    onclick="window.currentSelectedNodeId = '${safeId}'; document.getElementById('struct-target').value = '${safeName}'; window.runStructural('${cmd}', '${safeId}')">
                    <div class="font-bold text-cyan-400">${n.name} <span class="text-slate-400 font-normal uppercase text-[10px]">(${n.kind})</span></div>
                    <div class="text-slate-300 mt-1 truncate" title="${n.file_path}">${n.file_path} (L${n.start_line}-${n.end_line})</div>
                </div>`;
            });
            html += `</div>`;
            panel.innerHTML = html;
            return;
        }

        if (cmd === "find") {
            const n = data.data;
            window.currentSelectedNodeId = n.id; 
            const codeString = n.source_code || n.code || (n.kind === "module" ? "# Source code omitted for entire modules to save space." : "# Source code not available.");
            
            panel.innerHTML = `
                <h3 class="font-bold text-sm text-cyan-400 mb-1">${n.name}</h3>
                <div class="flex gap-2 text-xs mb-2">
                    <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 uppercase">${n.kind}</span>
                    <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300">L${n.start_line || 0}-${n.end_line || 0}</span>
                </div>
                <p class="mb-2"><b>File:</b> ${n.file_path || n.file}</p>
                <div class="mt-3 text-slate-400"><b>Docstring:</b>
                    <div class="max-h-24 overflow-y-auto bg-slate-950 p-2 rounded mt-1 border border-border">${escapeHTML(n.docstring || "No docstring")}</div>
                </div>
                <div class="mt-3 text-slate-400"><b>Source Code:</b>
                    <pre class="bg-slate-950 p-2 rounded text-[10px] overflow-auto text-emerald-400 mt-1 border border-border max-h-64 scrollbar-thin">${escapeHTML(codeString)}</pre>
                </div>
            `;
        } else {
            const isEmpty = !data.data || (Array.isArray(data.data) && data.data.length === 0) || (typeof data.data === 'object' && Object.keys(data.data).length === 0);

            if (isEmpty) {
                panel.innerHTML = `
                    <h3 class="font-bold mb-2 uppercase text-cyan-400">${cmd} Results for '${target}'</h3>
                    <div class="p-3 bg-slate-900 border border-slate-700 rounded text-slate-400 text-xs text-center mt-4">
                        No structural connections found.<br/><br/>
                        <span class="italic text-[10px]">Note: Modules typically have IMPORTS and DEFINES, but do not have direct CALLERS or CALLEES. Try selecting a specific function instead.</span>
                    </div>
                `;
            } else {
                panel.innerHTML = `
                    <h3 class="font-bold mb-2 uppercase text-cyan-400">${cmd} Results for '${target}'</h3>
                    <pre class="bg-slate-950 p-2 rounded border border-border text-[10px] text-emerald-400 whitespace-pre-wrap overflow-y-auto max-h-[60vh]">${JSON.stringify(data.data, null, 2)}</pre>
                `;
            }
        }
    } catch (err) {
        panel.innerHTML = `<div class="text-rose-400 text-sm">Error connecting to backend: ${err.message}</div>`;
    }
}

window.runSemantic = async function() {
    const q = document.getElementById('semantic-input').value.trim();
    if (!q) return;

    const cont = document.getElementById('semantic-results');
    cont.innerHTML = '<div class="text-slate-500 italic text-center mt-10 text-xs">Searching AI vectors...</div>';

    const topK = parseInt(localStorage.getItem('cg_topk') || '5');

    try {
        const res = await fetch(`/api/query/semantic?q=${encodeURIComponent(q)}&top_k=${topK}`);
        const data = await res.json();
        
        if (data.status === "error") {
            cont.innerHTML = `<div class="text-rose-400 text-xs p-2">${data.message}</div>`;
            return;
        }

        cont.innerHTML = data.results.map(r => {
            const safeId = r.id.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            const safeName = r.name.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            
            return `
            <div class="p-3 bg-slate-900 border border-border rounded text-xs cursor-pointer hover:border-cyan-500 transition-colors" 
                onclick="window.currentSelectedNodeId = '${safeId}'; document.getElementById('struct-target').value = '${safeName}'; window.setTab('structural'); window.runStructural('find', '${safeId}');">
                <div class="flex justify-between items-center mb-1">
                    <div class="flex items-center gap-2">
                        <span class="px-1.5 py-0.5 rounded bg-slate-800 text-[9px] text-slate-300 uppercase">${r.kind}</span>
                        <b class="text-slate-200 text-sm">${r.name}</b>
                    </div>
                    <span class="text-emerald-400 font-bold">${r.score}%</span>
                </div>
                <div class="text-slate-500 truncate" title="${r.file_path}">
                    ${r.file_path} (L${r.start_line}-${r.end_line})
                </div>
            </div>`;
        }).join('');
    } catch (err) {
        cont.innerHTML = `<div class="text-rose-400 text-xs text-center mt-10">Error running semantic search.</div>`;
    }
}

window.clearChat = function() {
    window.chatMessageHistory = [];
    const hist = document.getElementById('chat-history');
    hist.innerHTML = '<div class="text-slate-500 italic text-xs text-center mt-4">Ask architectural questions. The agent will read the graph and source code.</div>';
}

window.sendChat = async function() {
    const inp = document.getElementById('chat-input');
    const q = inp.value.trim();
    if (!q) return;
    
    const hist = document.getElementById('chat-history');
    hist.innerHTML += `<div class="bg-blue-900/20 text-blue-200 p-2 rounded self-end max-w-[85%] text-xs border border-blue-800/30"><b>You:</b> ${q}</div>`;
    inp.value = '';
    
    const btn = document.getElementById('btn-send-chat'); 
    btn.disabled = true; 
    btn.innerText = 'Analyzing...';

    const maxDepth = parseInt(localStorage.getItem('cg_depth') || '2');

    try {
        const res = await fetch('/api/query/chat', { 
            method: 'POST', headers: { 'Content-Type': 'application/json' }, 
            body: JSON.stringify({ question: q, depth: maxDepth, history: window.chatMessageHistory }) 
        });
        const data = await res.json();
        
        const answerText = data.answer || data.message;

        window.chatMessageHistory.push({ role: 'user', content: q });
        window.chatMessageHistory.push({ role: 'assistant', content: answerText });

        if (window.chatMessageHistory.length > 6) {
            window.chatMessageHistory = window.chatMessageHistory.slice(window.chatMessageHistory.length - 6);
        }

        hist.innerHTML += `
            <div class="bg-slate-800 text-slate-200 p-3 rounded self-start chat-bubble border border-slate-700 w-full shadow-lg">
                <div class="text-[10px] text-cyan-400 mb-2 font-mono uppercase tracking-wider border-b border-slate-700 pb-1">
                    Context: ${data.matched_symbol || 'N/A'}
                </div>
                <div class="prose prose-invert prose-sm text-xs leading-relaxed w-full max-w-none">
                    ${marked.parse(answerText)}
                </div>
            </div>`;
    } catch(e) { 
        hist.innerHTML += `<div class="text-rose-400 text-xs">Error: ${e.message}</div>`; 
    }
    
    btn.disabled = false; 
    btn.innerText = 'Send';
    hist.scrollTop = hist.scrollHeight;
}

window.loadConfig = async function() {
    const res = await fetch('/api/config');
    const data = await res.json();
    if (data.configured) {
        document.getElementById('cfg-provider').value = data.provider;
        document.getElementById('cfg-model').value = data.model;
        document.getElementById('cfg-base-url').value = data.base_url || '';
    }
    
    document.getElementById('cfg-depth').value = localStorage.getItem('cg_depth') || '2';
    document.getElementById('cfg-topk').value = localStorage.getItem('cg_topk') || '5';
}

window.saveConfig = async function() {
    await fetch('/api/config', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            provider: document.getElementById('cfg-provider').value,
            model: document.getElementById('cfg-model').value,
            base_url: document.getElementById('cfg-base-url').value,
            api_key: document.getElementById('cfg-api-key').value
        })
    });

    localStorage.setItem('cg_depth', document.getElementById('cfg-depth').value);
    localStorage.setItem('cg_topk', document.getElementById('cfg-topk').value);

    window.toggleModal('config-modal');
    
    const btn = document.querySelector('button[onclick="window.toggleModal(\'config-modal\')"]');
    const originalText = btn.innerHTML;
    btn.innerHTML = 'Saved';
    setTimeout(() => btn.innerHTML = originalText, 2000);
}

// Initialize application
initGraph();