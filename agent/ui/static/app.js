/**
 * Apollo Agent Cloud V1.7.R - Main Application (Rust Hybrid)
 * UI Logic for Files & Databases Audit (Cloud Mode)
 *
 * IMPORTANT: This is Agent Cloud - NO SCORING here
 * Scoring happens on Hub (IP protected)
 *
 * V1.7.R: Rust Hybrid Module (Sprint 61) - 2x performance boost
 */

// State
const state = {
    files: {
        sources: [],
        discovered: [],
        sessionId: null,
        eventSource: null,
        results: null
    },
    db: {
        sources: [],
        discovered: [],
        sessionId: null,
        eventSource: null,
        results: null
    },
    cloud: {
        drives: [],
        sessionId: null,
        eventSource: null,
        results: null
    },
    directory: {
        sessionId: null,
        eventSource: null,
        results: null
    },
    app: {
        sessionId: null,
        eventSource: null,
        results: null
    }
};

// === TAB NAVIGATION (Sprint 87) ===
function switchTab(tabId) {
    // Hide all panels
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    // Deactivate all tab buttons
    document.querySelectorAll('.tab-nav button').forEach(b => b.classList.remove('active'));
    // Show selected panel
    const panel = document.getElementById('panel-' + tabId);
    if (panel) panel.classList.add('active');
    // Activate tab button
    const btn = document.getElementById('tab-btn-' + tabId);
    if (btn) btn.classList.add('active');
    // Reinitialize Lucide icons for newly visible content
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
}

// === XSS Protection ===
function escapeHtml(str) {
    if (typeof str !== 'string') return str;
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// === LOCAL STORAGE PERSISTENCE ===
function saveToLocalStorage() {
    localStorage.setItem('apollo_agent_file_sources', JSON.stringify(state.files.sources));
    // Don't save DB credentials to localStorage (security)
    console.log('[STORAGE] Saved file sources');
}

function loadFromLocalStorage() {
    try {
        const saved = localStorage.getItem('apollo_agent_file_sources');
        if (saved) {
            state.files.sources = JSON.parse(saved);
            console.log(`[STORAGE] Restored ${state.files.sources.length} file sources`);
        }
    } catch (e) {
        console.error('[STORAGE] Error loading:', e);
    }
}

// Load on startup
loadFromLocalStorage();

// Render restored sources after DOM ready
document.addEventListener('DOMContentLoaded', function() {
    if (state.files.sources.length > 0) {
        renderFilesSources();
    }
    // Load Hub connection status for footer
    loadHubConnectionStatus();
    // KI-028: Refresh every 60s so other tabs catch key/tier changes
    setInterval(() => {
        if (document.visibilityState === 'visible') loadHubConnectionStatus();
    }, 60000);
});

// ============================================================================
// HUB CONNECTION STATUS (Footer Indicator)
// ============================================================================

async function loadHubConnectionStatus() {
    const dot = document.getElementById('hub-dot');
    const clientName = document.getElementById('hub-client-name');
    const hubStatus = document.getElementById('hub-status-text');

    try {
        const response = await fetch('/api/v2/hub-client-info');
        const data = await response.json();

        if (data.connected) {
            // Connected OK
            if (dot) {
                dot.textContent = '●';
                dot.style.color = '#10b981'; // green
            }
            if (clientName) {
                const tierLabel = (data.tier || 'free').charAt(0).toUpperCase() + (data.tier || 'free').slice(1);
                clientName.textContent = (data.name || 'Unknown') + ' | ' + tierLabel;
                clientName.style.color = '#d1d5db';
            }
            if (hubStatus) {
                hubStatus.textContent = '● Online';
                hubStatus.style.color = '#10b981'; // green
            }
            // Sprint 88B: store tier and apply restrictions
            if (data.tier) {
                AUTH.setTier(data.tier);
            }
            if (data.is_admin) {
                AUTH.setTier('enterprise'); // Admin sees everything
            }
            applyTierRestrictions();
        } else {
            // Not connected
            if (dot) {
                dot.textContent = '○';
                dot.style.color = '#ef4444'; // red
            }
            if (clientName) {
                clientName.textContent = data.reason || 'Hors ligne';
                clientName.style.color = '#ef4444';
            }
            if (hubStatus) {
                hubStatus.textContent = '○ Offline';
                hubStatus.style.color = '#ef4444'; // red
            }
        }
    } catch (error) {
        console.error('[HUB] Connection check failed:', error);
        if (dot) {
            dot.textContent = '○';
            dot.style.color = '#f59e0b'; // amber
        }
        if (clientName) {
            clientName.textContent = 'Erreur';
            clientName.style.color = '#f59e0b';
        }
        if (hubStatus) {
            hubStatus.textContent = '○ Error';
            hubStatus.style.color = '#f59e0b';
        }
    }
}

// ============================================================================
// TIER RESTRICTIONS (Sprint 88B - Free Tier Enforcement)
// ============================================================================

/**
 * Apply tier-based UI restrictions.
 * Beta period: all connectors unlocked for all tiers (Sprint 115 L2).
 */
function applyTierRestrictions() {
    const dbBtn = document.getElementById('db-start-btn');
    const cloudBtn = document.getElementById('cloud-start-btn');

    [dbBtn, cloudBtn].forEach(btn => {
        if (!btn) return;
        btn.disabled = false;
        btn.style.opacity = '';
        btn.style.cursor = '';
    });
}

// ============================================================================
// FILES AUTO-DISCOVER
// ============================================================================

async function discoverFiles() {
    const btn = document.getElementById('files-discover-btn');
    btn.disabled = true;
    btn.textContent = 'Scanning...';

    try {
        const response = await fetch('/api/v2/discover/files');
        const data = await response.json();

        state.files.discovered = data.sources || [];
        renderFilesDiscovered();

        document.getElementById('files-discovered').style.display = 'block';
    } catch (err) {
        console.error('Discover files error:', err);
        alert('Error scanning folders: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Auto-Discover';
    }
}

function renderFilesDiscovered() {
    const list = document.getElementById('files-discovered-list');

    // Sort alphabetically
    state.files.discovered.sort((a, b) => a.name.localeCompare(b.name));

    // OPT-OUT: Accessible sources checked by default (except default_excluded)
    state.files.sources = [];
    state.files.discovered.forEach(src => {
        if (src.accessible && !src.default_excluded) {
            state.files.sources.push(src.path);
        }
    });

    list.innerHTML = state.files.discovered.map((src, i) => {
        const isChecked = src.accessible && !src.default_excluded;
        const isDisabled = !src.accessible;
        const excludedClass = src.default_excluded ? 'default-excluded' : '';

        return `
            <li class="discovered-item ${excludedClass}">
                <label>
                    <input type="checkbox"
                        id="files-disc-${i}"
                        ${isChecked ? 'checked' : ''}
                        ${isDisabled ? 'disabled' : ''}
                        onchange="toggleFilesDiscovered(${i})"
                    />
                    <span class="disc-name">${escapeHtml(src.name)}</span>
                    <span class="disc-info">${formatFileCount(src.files_count)} files</span>
                    ${src.default_excluded ? '<span class="disc-excluded">(large/system)</span>' : ''}
                </label>
            </li>
        `;
    }).join('');

    renderFilesSources();
    console.log(`[DISCOVER] Files: ${state.files.discovered.length} found, ${state.files.sources.length} selected`);
}

function toggleFilesDiscovered(index) {
    const checkbox = document.getElementById(`files-disc-${index}`);
    const src = state.files.discovered[index];

    if (checkbox.checked) {
        if (!state.files.sources.includes(src.path)) {
            state.files.sources.push(src.path);
        }
    } else {
        const idx = state.files.sources.indexOf(src.path);
        if (idx > -1) state.files.sources.splice(idx, 1);
    }
    renderFilesSources();
}

function formatFileCount(count) {
    if (count >= 10000) return '10K+';
    if (count >= 1000) return (count / 1000).toFixed(1) + 'K';
    return count;
}

// ============================================================================
// FILES AUDIT
// ============================================================================

function addFilesSource() {
    const input = document.getElementById('files-path-input');
    const path = input.value.trim();
    if (!path) return;

    state.files.sources.push(path);
    renderFilesSources();
    input.value = '';
}

function removeFilesSource(index) {
    state.files.sources.splice(index, 1);
    renderFilesSources();
}

function renderFilesSources() {
    const list = document.getElementById('files-sources-list');
    list.innerHTML = state.files.sources.map((src, i) => `
        <li>
            <span>${escapeHtml(src)}</span>
            <button onclick="removeFilesSource(${i})">&times;</button>
        </li>
    `).join('');
    saveToLocalStorage();
}

async function startFilesAudit() {
    if (state.files.sources.length === 0) {
        alert('Add at least one source path');
        return;
    }

    const btn = document.getElementById('files-start-btn');
    btn.disabled = true;
    btn.textContent = 'Starting...';

    // Show progress
    document.getElementById('files-progress').style.display = 'block';
    document.getElementById('files-scoring-placeholder').style.display = 'none';

    // Show STOP button
    updateStopButtonVisibility(true);

    // Reset stats
    resetFilesStats();

    console.log(`[AUDIT] Starting files audit: ${state.files.sources.length} sources`);

    try {
        const response = await fetch('/api/v2/files/audit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sources: state.files.sources, excluded_sources: [] })
        });

        if (!response.ok) throw new Error(await response.text());

        const { session_id } = await response.json();
        state.files.sessionId = session_id;

        // Connect to SSE
        connectFilesSSE(session_id);

    } catch (err) {
        alert('Error starting audit: ' + err.message);
        btn.disabled = false;
        btn.textContent = 'Start Files Audit';
    }
}

function connectFilesSSE(sessionId) {
    const eventSource = new EventSource(`/api/v2/files/progress/${sessionId}`);
    state.files.eventSource = eventSource;

    eventSource.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        updateFilesProgress(data);
    });

    eventSource.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data);
        eventSource.close();
        onFilesComplete(data);
    });

    eventSource.addEventListener('error', (e) => {
        eventSource.close();
        onFilesError(e);
    });

    eventSource.onerror = () => {
        eventSource.close();
        onFilesError(new Error('SSE connection lost'));
    };
}

function updateFilesProgress(data) {
    // Progress display is now static HTML with spinning icon
    // No need to update text - just update stats
    if (data.stats) {
        updateFilesStats(data.stats);
    }
}

function updateFilesStats(stats) {
    document.getElementById('files-discovered-count').textContent =
        stats.files_discovered ?? 'En cours...';
    document.getElementById('files-analyzed-count').textContent =
        stats.files_analyzed ?? 'En cours...';
    document.getElementById('files-pii-count').textContent =
        stats.files_with_pii ?? '0';
}

function resetFilesStats() {
    document.getElementById('files-discovered-count').textContent = '-';
    document.getElementById('files-analyzed-count').textContent = '-';
    document.getElementById('files-pii-count').textContent = '-';
}

function onFilesComplete(data) {
    // Store the full result (same JSON sent to Hub) for export
    state.files.results = data.result || data;

    const btn = document.getElementById('files-start-btn');
    btn.disabled = false;
    btn.textContent = 'Start Files Audit';

    document.getElementById('files-progress').style.display = 'none';

    // Hide STOP button
    updateStopButtonVisibility(false);

    // Update final stats
    if (data.stats) {
        updateFilesStats(data.stats);
    }

    // Show export button
    document.getElementById('files-export-btn').style.display = 'block';

    // Show scoring placeholder (Cloud mode)
    document.getElementById('files-scoring-placeholder').style.display = 'block';

    // Display errors if any (Sprint 39)
    if (state.files.sessionId) {
        displayErrors(state.files.sessionId, 'files');
    }

    // Show status message
    if (data.status === 'complete') {
        showStatus('Files audit complete! Check Hub Dashboard for scores.', 'success');
    } else if (data.error) {
        showStatus('Files audit error: ' + data.error, 'error');
    }

    console.log('[AUDIT] Files complete:', data);
}

function onFilesError(err) {
    console.error('Files SSE error:', err);
    const btn = document.getElementById('files-start-btn');
    btn.disabled = false;
    btn.textContent = 'Start Files Audit';
    document.getElementById('files-progress').style.display = 'none';
    updateStopButtonVisibility(false);
    showStatus('Audit error. Check console for details.', 'error');
}

// ============================================================================
// DATABASES AUTO-DISCOVER
// ============================================================================

async function discoverDatabases() {
    const btn = document.getElementById('db-discover-btn');
    btn.disabled = true;
    btn.textContent = 'Scanning ports...';

    try {
        const response = await fetch('/api/v2/discover/databases');
        const data = await response.json();

        state.db.discovered = data.sources || [];
        renderDbDiscovered();

        document.getElementById('db-discovered').style.display = 'block';

        if (state.db.discovered.length === 0) {
            alert('No databases found on localhost.');
        }
    } catch (err) {
        console.error('Discover databases error:', err);
        alert('Error scanning ports: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Auto-Discover';
    }
}

function renderDbDiscovered() {
    const list = document.getElementById('db-discovered-list');

    state.db.discovered.sort((a, b) => a.name.localeCompare(b.name));

    list.innerHTML = state.db.discovered.map((src, i) => `
        <li class="discovered-item">
            <label>
                <input type="checkbox"
                    id="db-disc-${i}"
                    checked
                    onchange="toggleDbDiscovered(${i})"
                />
                <span class="disc-name">${escapeHtml(src.name)}</span>
                <span class="disc-info">:${src.port}</span>
            </label>
            <div class="db-creds" id="db-creds-${i}" style="margin-left: 25px; margin-top: 5px;">
                <input type="text" id="db-disc-name-${i}" placeholder="database name" style="width: 120px; margin-right: 5px;" />
                <input type="text" id="db-disc-user-${i}" placeholder="username" style="width: 100px; margin-right: 5px;" />
                <input type="password" id="db-disc-pass-${i}" placeholder="password" style="width: 100px;" />
            </div>
        </li>
    `).join('');

    console.log(`[DISCOVER] Databases: ${state.db.discovered.length} found`);
}

function toggleDbDiscovered(index) {
    const checkbox = document.getElementById(`db-disc-${index}`);
    const credsDiv = document.getElementById(`db-creds-${index}`);

    credsDiv.style.display = checkbox.checked ? 'block' : 'none';
}

function collectDbDiscoveredSources() {
    const sources = [];

    state.db.discovered.forEach((src, i) => {
        const checkbox = document.getElementById(`db-disc-${i}`);
        if (checkbox && checkbox.checked) {
            const dbName = document.getElementById(`db-disc-name-${i}`).value.trim();
            const user = document.getElementById(`db-disc-user-${i}`).value.trim();
            const pass = document.getElementById(`db-disc-pass-${i}`).value;

            if (dbName) {
                sources.push({
                    db_type: src.db_type,
                    host: src.host,
                    port: src.port,
                    database: dbName,
                    username: user,
                    password: pass
                });
            }
        }
    });

    return sources;
}

// ============================================================================
// DATABASES AUDIT
// ============================================================================

function addDbSource() {
    const typeSelect = document.getElementById('db-type-select');
    const hostInput = document.getElementById('db-host-input');
    const nameInput = document.getElementById('db-name-input');
    const userInput = document.getElementById('db-user-input');
    const passInput = document.getElementById('db-pass-input');

    const hostParts = hostInput.value.trim().split(':');
    const host = hostParts[0] || 'localhost';
    const port = parseInt(hostParts[1]) || 5432;

    if (!nameInput.value.trim()) {
        alert('Database name required');
        return;
    }

    state.db.sources.push({
        db_type: typeSelect.value,
        host: host,
        port: port,
        database: nameInput.value.trim(),
        username: userInput.value.trim(),
        password: passInput.value
    });

    renderDbSources();

    // Clear inputs
    hostInput.value = '';
    nameInput.value = '';
    userInput.value = '';
    passInput.value = '';
}

function removeDbSource(index) {
    state.db.sources.splice(index, 1);
    renderDbSources();
}

function renderDbSources() {
    const list = document.getElementById('db-sources-list');
    list.innerHTML = state.db.sources.map((src, i) => `
        <li>
            <span>${escapeHtml(src.db_type)}://${escapeHtml(src.host)}:${src.port}/${escapeHtml(src.database)}</span>
            <button onclick="removeDbSource(${i})">&times;</button>
        </li>
    `).join('');
}

async function startDbAudit() {
    // Collect from discovered + manual
    const discoveredSources = collectDbDiscoveredSources();
    const allSources = [...discoveredSources, ...state.db.sources];

    if (allSources.length === 0) {
        alert('Add at least one database (fill database name and credentials)');
        return;
    }

    const btn = document.getElementById('db-start-btn');
    btn.disabled = true;
    btn.textContent = 'Starting...';

    document.getElementById('db-progress').style.display = 'block';
    document.getElementById('db-scoring-placeholder').style.display = 'none';

    // Show STOP button
    updateStopButtonVisibility(true);

    resetDbStats();

    console.log(`[AUDIT] Starting DB audit: ${allSources.length} databases`);

    try {
        const response = await fetch('/api/v2/databases/audit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sources: allSources, excluded_sources: [] })
        });

        if (!response.ok) throw new Error(await response.text());

        const { session_id } = await response.json();
        state.db.sessionId = session_id;

        connectDbSSE(session_id);

    } catch (err) {
        alert('Error starting DB audit: ' + err.message);
        btn.disabled = false;
        btn.textContent = 'Start DB Audit';
    }
}

function connectDbSSE(sessionId) {
    const eventSource = new EventSource(`/api/v2/databases/progress/${sessionId}`);
    state.db.eventSource = eventSource;

    eventSource.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        updateDbProgress(data);
    });

    eventSource.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data);
        eventSource.close();
        onDbComplete(data);
    });

    eventSource.addEventListener('error', (e) => {
        eventSource.close();
        onDbError(e);
    });

    eventSource.onerror = () => {
        eventSource.close();
        onDbError(new Error('SSE connection lost'));
    };
}

function updateDbProgress(data) {
    // Progress display is now static HTML with spinning icon
    // No need to update text - just update stats
    if (data.stats) {
        updateDbStats(data.stats);
    }
}

function updateDbStats(stats) {
    document.getElementById('db-tables-count').textContent =
        stats.tables_discovered ?? 'En cours...';
    document.getElementById('db-analyzed-count').textContent =
        stats.tables_analyzed ?? 'En cours...';
    document.getElementById('db-pii-count').textContent =
        stats.tables_with_pii ?? '0';
}

function resetDbStats() {
    document.getElementById('db-tables-count').textContent = '-';
    document.getElementById('db-analyzed-count').textContent = '-';
    document.getElementById('db-pii-count').textContent = '-';
}

function onDbComplete(data) {
    // Store the full result (same JSON sent to Hub) for export
    state.db.results = data.result || data;

    const btn = document.getElementById('db-start-btn');
    btn.disabled = false;
    btn.textContent = 'Start DB Audit';

    document.getElementById('db-progress').style.display = 'none';

    // Hide STOP button
    updateStopButtonVisibility(false);

    if (data.stats) {
        updateDbStats(data.stats);
    }

    // Show export button
    document.getElementById('db-export-btn').style.display = 'block';

    document.getElementById('db-scoring-placeholder').style.display = 'block';

    // Display errors if any (Sprint 39)
    if (state.db.sessionId) {
        displayErrors(state.db.sessionId, 'databases');
    }

    if (data.status === 'complete') {
        showStatus('Database audit complete! Check Hub Dashboard for scores.', 'success');
    } else if (data.error) {
        showStatus('Database audit error: ' + data.error, 'error');
    }

    console.log('[AUDIT] DB complete:', data);
}

function onDbError(err) {
    console.error('DB SSE error:', err);
    const btn = document.getElementById('db-start-btn');
    btn.disabled = false;
    btn.textContent = 'Start DB Audit';
    document.getElementById('db-progress').style.display = 'none';
    updateStopButtonVisibility(false);
    showStatus('DB Audit error. Check console for details.', 'error');
}

// ============================================================================
// EXPORT JSON (Offline/Backup)
// ============================================================================

function exportFilesReport() {
    if (!state.files.results) {
        alert('No files audit results to export');
        return;
    }
    const timestamp = new Date().toISOString().split('T')[0];
    downloadJson(state.files.results, `APOLLO_files_audit_${timestamp}.json`);
}

function exportDbReport() {
    if (!state.db.results) {
        alert('No database audit results to export');
        return;
    }
    const timestamp = new Date().toISOString().split('T')[0];
    downloadJson(state.db.results, `APOLLO_db_audit_${timestamp}.json`);
}

function downloadJson(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    console.log(`[EXPORT] Downloaded: ${filename}`);
}

// ============================================================================
// STATUS MESSAGES
// ============================================================================

function showStatus(message, type) {
    const section = document.getElementById('status-messages');
    const content = document.getElementById('status-content');

    section.style.display = 'block';
    content.innerHTML = `
        <p class="${type === 'success' ? 'success-indicator' : 'error-indicator'}">
            ${type === 'success' ? '✓' : '✗'} ${escapeHtml(message)}
        </p>
    `;

    // Auto-hide after 10s
    setTimeout(() => {
        section.style.display = 'none';
    }, 10000);
}

// ============================================================================
// STOP SCAN & RESET DASHBOARD
// ============================================================================

/**
 * Stop the current scan (FILES or DB).
 * Calls backend to abort subprocess and updates UI.
 */
async function stopScan() {
    const stopBtn = document.getElementById('stop-scan-btn');
    stopBtn.disabled = true;
    stopBtn.textContent = 'Stopping...';

    try {
        const response = await fetch('/api/v2/scan/abort', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();

        if (data.status === 'aborted') {
            showStatus('Scan interrompu', 'error');

            // Close any open SSE connections
            if (state.files.eventSource) {
                state.files.eventSource.close();
                state.files.eventSource = null;
            }
            if (state.db.eventSource) {
                state.db.eventSource.close();
                state.db.eventSource = null;
            }
            if (state.cloud.eventSource) {
                state.cloud.eventSource.close();
                state.cloud.eventSource = null;
            }
            if (state.directory.eventSource) {
                state.directory.eventSource.close();
                state.directory.eventSource = null;
            }

            // Reset buttons
            document.getElementById('files-start-btn').disabled = false;
            document.getElementById('files-start-btn').textContent = 'Start Files Audit';
            document.getElementById('db-start-btn').disabled = false;
            document.getElementById('db-start-btn').textContent = 'Start DB Audit';
            document.getElementById('cloud-start-btn').disabled = false;
            document.getElementById('cloud-start-btn').textContent = 'Start Cloud Audit';
            document.getElementById('dir-start-btn').disabled = false;
            document.getElementById('dir-start-btn').textContent = 'Start Directory Audit';

            // Hide progress bars
            document.getElementById('files-progress').style.display = 'none';
            document.getElementById('db-progress').style.display = 'none';
            document.getElementById('cloud-progress').style.display = 'none';
            document.getElementById('dir-progress').style.display = 'none';
        } else {
            showStatus('Erreur lors de l\'arrêt: ' + (data.error || 'Unknown'), 'error');
        }
    } catch (err) {
        console.error('Stop scan error:', err);
        showStatus('Erreur: ' + err.message, 'error');
    } finally {
        stopBtn.disabled = false;
        stopBtn.innerHTML = '<i data-lucide="alert-triangle" style="width: 16px; height: 16px; margin-right: 6px;"></i>Stop Scan';
        stopBtn.style.display = 'none';
        // Reinitialize Lucide icons
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }
}

/**
 * Reset the dashboard to initial state.
 * Clears all sources, results, and local storage.
 */
function resetDashboard() {
    // Confirmation dialog
    const confirmed = confirm('Effacer toutes les données et recommencer ?\n\nCette action va:\n- Supprimer toutes les sources ajoutées\n- Effacer les résultats affichés\n- Remettre l\'interface à zéro');

    if (!confirmed) {
        return;
    }

    console.log('[RESET] Resetting dashboard...');

    // Close any open SSE connections
    if (state.files.eventSource) {
        state.files.eventSource.close();
        state.files.eventSource = null;
    }
    if (state.db.eventSource) {
        state.db.eventSource.close();
        state.db.eventSource = null;
    }
    if (state.cloud.eventSource) {
        state.cloud.eventSource.close();
        state.cloud.eventSource = null;
    }
    if (state.directory.eventSource) {
        state.directory.eventSource.close();
        state.directory.eventSource = null;
    }

    // Reset state
    state.files.sources = [];
    state.files.discovered = [];
    state.files.sessionId = null;
    state.files.results = null;

    state.db.sources = [];
    state.db.discovered = [];
    state.db.sessionId = null;
    state.db.results = null;

    state.cloud.drives = [];
    state.cloud.sessionId = null;
    state.cloud.results = null;

    state.directory.sessionId = null;
    state.directory.results = null;

    // Clear localStorage
    localStorage.removeItem('apollo_agent_file_sources');
    sessionStorage.clear();

    // Reset UI - Files
    document.getElementById('files-sources-list').innerHTML = '';
    document.getElementById('files-discovered-list').innerHTML = '';
    document.getElementById('files-discovered').style.display = 'none';
    document.getElementById('files-progress').style.display = 'none';
    document.getElementById('files-scoring-placeholder').style.display = 'none';
    document.getElementById('files-export-btn').style.display = 'none';
    document.getElementById('files-start-btn').disabled = false;
    document.getElementById('files-start-btn').textContent = 'Start Files Audit';
    resetFilesStats();

    // Reset UI - Databases
    document.getElementById('db-sources-list').innerHTML = '';
    document.getElementById('db-discovered-list').innerHTML = '';
    document.getElementById('db-discovered').style.display = 'none';
    document.getElementById('db-progress').style.display = 'none';
    document.getElementById('db-scoring-placeholder').style.display = 'none';
    document.getElementById('db-export-btn').style.display = 'none';
    document.getElementById('db-start-btn').disabled = false;
    document.getElementById('db-start-btn').textContent = 'Start DB Audit';
    resetDbStats();

    // Reset UI - Cloud
    document.getElementById('cloud-tenant-id').value = '';
    document.getElementById('cloud-client-id').value = '';
    document.getElementById('cloud-client-secret').value = '';
    document.getElementById('cloud-drive-select').innerHTML = '<option value="all">Scan All Drives (click List Drives first)</option>';
    document.getElementById('cloud-path-input').value = '/';
    document.getElementById('cloud-progress').style.display = 'none';
    document.getElementById('cloud-scoring-placeholder').style.display = 'none';
    document.getElementById('cloud-export-btn').style.display = 'none';
    document.getElementById('cloud-start-btn').disabled = false;
    document.getElementById('cloud-start-btn').textContent = 'Start Cloud Audit';
    resetCloudStats();

    // Reset UI - Directory
    document.getElementById('dir-host').value = '';
    document.getElementById('dir-port').value = '';
    document.getElementById('dir-bind-dn').value = '';
    document.getElementById('dir-bind-password').value = '';
    document.getElementById('dir-base-dn').value = '';
    document.getElementById('dir-use-ssl').checked = false;
    document.getElementById('dir-progress').style.display = 'none';
    document.getElementById('dir-scoring-placeholder').style.display = 'none';
    document.getElementById('dir-export-btn').style.display = 'none';
    document.getElementById('dir-start-btn').disabled = false;
    document.getElementById('dir-start-btn').textContent = 'Start Directory Audit';
    resetDirectoryStats();

    // Clear error panels (Sprint 39)
    clearErrorPanel('files');
    clearErrorPanel('databases');
    clearErrorPanel('cloud');
    clearErrorPanel('directory');

    // Hide status messages
    document.getElementById('status-messages').style.display = 'none';

    // Hide stop button
    document.getElementById('stop-scan-btn').style.display = 'none';

    showStatus('Dashboard réinitialisé', 'success');
    console.log('[RESET] Dashboard reset complete');
}

/**
 * Show/hide STOP button based on scan state.
 * Called when scan starts/ends.
 */
function updateStopButtonVisibility(isScanning) {
    const stopBtn = document.getElementById('stop-scan-btn');
    if (stopBtn) {
        stopBtn.style.display = isScanning ? 'inline-flex' : 'none';
        // Reinitialize Lucide icons
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }
}

// ============================================================================
// CLOUD AUDIT (Sprint 35 - OneDrive/SharePoint)
// ============================================================================

/**
 * List available OneDrive/SharePoint drives.
 * Requires Azure AD credentials to be filled.
 */
async function listCloudDrives() {
    const tenantId = document.getElementById('cloud-tenant-id').value.trim();
    const clientId = document.getElementById('cloud-client-id').value.trim();
    const clientSecret = document.getElementById('cloud-client-secret').value;

    if (!tenantId || !clientId || !clientSecret) {
        alert('Please fill all Azure AD credentials (Tenant ID, Client ID, Client Secret)');
        return;
    }

    const btn = document.getElementById('cloud-list-drives-btn');
    btn.disabled = true;
    btn.textContent = 'Connecting...';

    try {
        const response = await fetch('/api/v2/cloud/drives', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tenant_id: tenantId,
                client_id: clientId,
                client_secret: clientSecret
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText);
        }

        const data = await response.json();
        state.cloud.drives = data.drives || [];

        // Populate select dropdown - OPT-OUT pattern (scan all by default)
        const select = document.getElementById('cloud-drive-select');
        select.innerHTML = '<option value="all">Scan All Drives (recommended)</option>';
        state.cloud.drives.forEach(drive => {
            select.innerHTML += `<option value="${escapeHtml(drive.id)}">${escapeHtml(drive.name)} (${escapeHtml(drive.driveType)})</option>`;
        });

        showStatus(`Found ${state.cloud.drives.length} drive(s) - "Scan All" selected by default`, 'success');
        console.log('[CLOUD] Drives listed:', state.cloud.drives);

    } catch (err) {
        console.error('List drives error:', err);
        alert('Error connecting to OneDrive: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'List Drives';
    }
}

/**
 * Start cloud audit (OneDrive/SharePoint scan).
 */
async function startCloudAudit() {
    const tenantId = document.getElementById('cloud-tenant-id').value.trim();
    const clientId = document.getElementById('cloud-client-id').value.trim();
    const clientSecret = document.getElementById('cloud-client-secret').value;
    const driveId = document.getElementById('cloud-drive-select').value;
    const cloudPath = document.getElementById('cloud-path-input').value.trim() || '/';

    if (!tenantId || !clientId || !clientSecret) {
        alert('Please fill all Azure AD credentials');
        return;
    }

    const btn = document.getElementById('cloud-start-btn');
    btn.disabled = true;
    btn.textContent = 'Starting...';

    // Show progress
    document.getElementById('cloud-progress').style.display = 'block';
    document.getElementById('cloud-scoring-placeholder').style.display = 'none';

    // Show STOP button
    updateStopButtonVisibility(true);

    // Reset stats
    resetCloudStats();

    console.log(`[AUDIT] Starting cloud audit: drive=${driveId}, path=${cloudPath}`);

    try {
        const response = await fetch('/api/v2/cloud/audit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tenant_id: tenantId,
                client_id: clientId,
                client_secret: clientSecret,
                drive_id: driveId,
                cloud_path: cloudPath
            })
        });

        if (!response.ok) throw new Error(await response.text());

        const { session_id } = await response.json();
        state.cloud.sessionId = session_id;

        // Connect to SSE
        connectCloudSSE(session_id);

    } catch (err) {
        alert('Error starting cloud audit: ' + err.message);
        btn.disabled = false;
        btn.textContent = 'Start Cloud Audit';
    }
}

function connectCloudSSE(sessionId) {
    const eventSource = new EventSource(`/api/v2/cloud/progress/${sessionId}`);
    state.cloud.eventSource = eventSource;

    eventSource.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        updateCloudProgress(data);
    });

    eventSource.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data);
        eventSource.close();
        onCloudComplete(data);
    });

    eventSource.addEventListener('error', (e) => {
        eventSource.close();
        onCloudError(e);
    });

    eventSource.onerror = () => {
        eventSource.close();
        onCloudError(new Error('SSE connection lost'));
    };
}

function updateCloudProgress(data) {
    // Progress display is now static HTML with spinning icon
    // No need to update text - just update stats
    if (data.stats) {
        updateCloudStats(data.stats);
    }
}

function updateCloudStats(stats) {
    document.getElementById('cloud-files-count').textContent =
        stats.files_count ?? 'En cours...';
    document.getElementById('cloud-size-total').textContent =
        formatBytes(stats.total_size ?? 0);
    document.getElementById('cloud-shared-count').textContent =
        stats.shared_files_count ?? '0';
    document.getElementById('cloud-pii-count').textContent =
        stats.files_with_pii ?? '0';
}

function resetCloudStats() {
    document.getElementById('cloud-files-count').textContent = '-';
    document.getElementById('cloud-size-total').textContent = '-';
    document.getElementById('cloud-shared-count').textContent = '-';
    document.getElementById('cloud-pii-count').textContent = '-';
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function onCloudComplete(data) {
    state.cloud.results = data.result || data;

    const btn = document.getElementById('cloud-start-btn');
    btn.disabled = false;
    btn.textContent = 'Start Cloud Audit';

    document.getElementById('cloud-progress').style.display = 'none';

    // Hide STOP button
    updateStopButtonVisibility(false);

    if (data.stats) {
        updateCloudStats(data.stats);
    }

    // Show export button
    document.getElementById('cloud-export-btn').style.display = 'block';

    // Show scoring placeholder
    document.getElementById('cloud-scoring-placeholder').style.display = 'block';

    // Display errors if any (Sprint 39)
    if (state.cloud.sessionId) {
        displayErrors(state.cloud.sessionId, 'cloud');
    }

    if (data.status === 'complete') {
        showStatus('Cloud audit complete! Check Hub Dashboard for scores.', 'success');
    } else if (data.error) {
        showStatus('Cloud audit error: ' + data.error, 'error');
    }

    console.log('[AUDIT] Cloud complete:', data);
}

function onCloudError(err) {
    console.error('Cloud SSE error:', err);
    const btn = document.getElementById('cloud-start-btn');
    btn.disabled = false;
    btn.textContent = 'Start Cloud Audit';
    document.getElementById('cloud-progress').style.display = 'none';
    updateStopButtonVisibility(false);
    showStatus('Cloud Audit error. Check console for details.', 'error');
}

function exportCloudReport() {
    if (!state.cloud.results) {
        alert('No cloud audit results to export');
        return;
    }
    const timestamp = new Date().toISOString().split('T')[0];
    downloadJson(state.cloud.results, `APOLLO_cloud_audit_${timestamp}.json`);
}

// ============================================================================
// ERROR PANEL (Sprint 39 - UI Error Panel)
// ============================================================================

/**
 * Fetch and display errors for a session.
 * Shows error panel only if errors exist.
 */
async function displayErrors(sessionId, auditType) {
    try {
        const response = await fetch(`/api/v2/errors/${sessionId}`);
        if (!response.ok) return;

        const data = await response.json();
        if (!data.errors || data.errors.length === 0) return;

        // Find or create error panel
        let panel = document.getElementById(`${auditType}-error-panel`);
        if (!panel) {
            // Create panel dynamically if not in HTML
            const column = document.getElementById(`${auditType === 'files' ? 'files' : auditType === 'databases' ? 'databases' : 'cloud'}-column`);
            if (!column) return;

            panel = document.createElement('div');
            panel.id = `${auditType}-error-panel`;
            panel.className = 'error-panel';
            panel.innerHTML = `<h4>Errors (${data.error_count})</h4><ul class="error-list"></ul>`;
            column.appendChild(panel);
        }

        // Populate errors
        const list = panel.querySelector('.error-list') || panel;
        list.innerHTML = data.errors.map(err => `
            <li class="error-item error-${err.level.toLowerCase()}">
                <span class="error-time">${err.timestamp.split('T')[1]?.split('.')[0] || ''}</span>
                <span class="error-source">[${escapeHtml(err.source)}]</span>
                <span class="error-msg">${escapeHtml(err.message)}</span>
            </li>
        `).join('');

        panel.style.display = 'block';
        console.log(`[ERROR-PANEL] ${auditType}: ${data.error_count} errors displayed`);

    } catch (e) {
        console.error('[ERROR-PANEL] Failed to fetch errors:', e);
    }
}

/**
 * Clear error panel for an audit type.
 */
function clearErrorPanel(auditType) {
    const panel = document.getElementById(`${auditType}-error-panel`);
    if (panel) {
        panel.style.display = 'none';
        const list = panel.querySelector('.error-list');
        if (list) list.innerHTML = '';
    }
}

// ============================================================================
// DIRECTORY AUDIT (Sprint 87 - LDAP/AD)
// ============================================================================

/**
 * Test LDAP/AD connection.
 */
async function testDirectoryConnection() {
    const host = document.getElementById('dir-host').value.trim();
    if (!host) {
        alert('Please enter a host address');
        return;
    }

    const btn = document.getElementById('dir-test-btn');
    btn.disabled = true;
    btn.textContent = 'Testing...';

    try {
        const response = await fetch('/api/v2/directory/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(getDirectoryConfig())
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText);
        }

        const data = await response.json();
        showStatus(`Connection OK - ${data.directory_type} - ${data.users_count} users`, 'success');
        console.log('[DIRECTORY] Test connection:', data);

    } catch (err) {
        console.error('Directory test error:', err);
        showStatus('Connection failed: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Test Connection';
    }
}

/**
 * Get directory config from form fields.
 */
function getDirectoryConfig() {
    return {
        host: document.getElementById('dir-host').value.trim(),
        port: parseInt(document.getElementById('dir-port').value) || 389,
        bind_dn: document.getElementById('dir-bind-dn').value.trim(),
        bind_password: document.getElementById('dir-bind-password').value,
        base_dn: document.getElementById('dir-base-dn').value.trim(),
        use_ssl: document.getElementById('dir-use-ssl').checked,
    };
}

/**
 * Start directory audit (LDAP/AD scan).
 */
async function startDirectoryAudit() {
    const host = document.getElementById('dir-host').value.trim();
    if (!host) {
        alert('Please enter a host address');
        return;
    }

    const btn = document.getElementById('dir-start-btn');
    btn.disabled = true;
    btn.textContent = 'Starting...';

    // Show progress
    document.getElementById('dir-progress').style.display = 'block';
    document.getElementById('dir-scoring-placeholder').style.display = 'none';

    // Show STOP button
    updateStopButtonVisibility(true);

    // Reset stats
    resetDirectoryStats();

    console.log(`[AUDIT] Starting directory audit: ${host}`);

    try {
        const response = await fetch('/api/v2/directory/audit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(getDirectoryConfig())
        });

        if (!response.ok) throw new Error(await response.text());

        const { session_id } = await response.json();
        state.directory.sessionId = session_id;

        // Connect to SSE
        connectDirectorySSE(session_id);

    } catch (err) {
        alert('Error starting directory audit: ' + err.message);
        btn.disabled = false;
        btn.textContent = 'Start Directory Audit';
    }
}

function connectDirectorySSE(sessionId) {
    const eventSource = new EventSource(`/api/v2/directory/progress/${sessionId}`);
    state.directory.eventSource = eventSource;

    eventSource.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        updateDirectoryProgress(data);
    });

    eventSource.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data);
        eventSource.close();
        onDirectoryComplete(data);
    });

    eventSource.addEventListener('error', (e) => {
        eventSource.close();
        onDirectoryError(e);
    });

    eventSource.onerror = () => {
        eventSource.close();
        onDirectoryError(new Error('SSE connection lost'));
    };
}

function updateDirectoryProgress(data) {
    if (data.stats) {
        updateDirectoryStats(data.stats);
    }
}

function updateDirectoryStats(stats) {
    document.getElementById('dir-users-count').textContent =
        stats.total_users ?? 'En cours...';
    document.getElementById('dir-disabled-count').textContent =
        stats.disabled_users ?? '0';
    document.getElementById('dir-dormant-count').textContent =
        stats.dormant_users ?? '0';
    document.getElementById('dir-service-count').textContent =
        stats.service_accounts ?? '0';
    document.getElementById('dir-groups-count').textContent =
        stats.total_groups ?? '0';
    document.getElementById('dir-admins-count').textContent =
        stats.total_admins ?? '0';
}

function resetDirectoryStats() {
    document.getElementById('dir-users-count').textContent = '-';
    document.getElementById('dir-disabled-count').textContent = '-';
    document.getElementById('dir-dormant-count').textContent = '-';
    document.getElementById('dir-service-count').textContent = '-';
    document.getElementById('dir-groups-count').textContent = '-';
    document.getElementById('dir-admins-count').textContent = '-';
}

function onDirectoryComplete(data) {
    state.directory.results = data.result || data;

    const btn = document.getElementById('dir-start-btn');
    btn.disabled = false;
    btn.textContent = 'Start Directory Audit';

    document.getElementById('dir-progress').style.display = 'none';

    // Hide STOP button
    updateStopButtonVisibility(false);

    if (data.stats) {
        updateDirectoryStats(data.stats);
    }

    // Show export button
    document.getElementById('dir-export-btn').style.display = 'block';

    // Show scoring placeholder
    document.getElementById('dir-scoring-placeholder').style.display = 'block';

    // Display errors if any
    if (state.directory.sessionId) {
        displayErrors(state.directory.sessionId, 'directory');
    }

    if (data.status === 'complete') {
        showStatus('Directory audit complete! Check Hub Dashboard for scores.', 'success');
    } else if (data.error) {
        showStatus('Directory audit error: ' + data.error, 'error');
    }

    console.log('[AUDIT] Directory complete:', data);
}

function onDirectoryError(err) {
    console.error('Directory SSE error:', err);
    const btn = document.getElementById('dir-start-btn');
    btn.disabled = false;
    btn.textContent = 'Start Directory Audit';
    document.getElementById('dir-progress').style.display = 'none';
    updateStopButtonVisibility(false);
    showStatus('Directory Audit error. Check console for details.', 'error');
}

function exportDirectoryReport() {
    if (!state.directory.results) {
        alert('No directory audit results to export');
        return;
    }
    const timestamp = new Date().toISOString().split('T')[0];
    downloadJson(state.directory.results, `APOLLO_directory_audit_${timestamp}.json`);
}

// ============================================================================
// APP AUDIT (Sprint 89 - ERP/CRM/SaaS)
// ============================================================================

/**
 * Get app connector config from form fields.
 */
function getAppConfig() {
    return {
        app_type: document.getElementById('app-type').value,
        api_token: document.getElementById('app-api-token').value,
        api_url: document.getElementById('app-api-url').value.trim(),
        use_2026_api: document.getElementById('app-use-2026-api').checked,
    };
}

/**
 * Test app connection (quick check).
 */
async function testAppConnection() {
    const token = document.getElementById('app-api-token').value;
    if (!token) {
        alert('Please enter an API token');
        return;
    }

    const btn = document.getElementById('app-test-btn');
    btn.disabled = true;
    btn.textContent = 'Testing...';

    try {
        const response = await fetch('/api/v2/app/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(getAppConfig())
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText);
        }

        const data = await response.json();
        showStatus(`Connection OK - ${data.app_type} - ${data.company_name}`, 'success');
        console.log('[APP] Test connection:', data);

    } catch (err) {
        console.error('App test error:', err);
        showStatus('Connection failed: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Test Connection';
    }
}

/**
 * Start app audit (ERP/CRM/SaaS scan).
 */
async function startAppAudit() {
    const token = document.getElementById('app-api-token').value;
    if (!token) {
        alert('Please enter an API token');
        return;
    }

    const btn = document.getElementById('app-start-btn');
    btn.disabled = true;
    btn.textContent = 'Starting...';

    // Show progress
    document.getElementById('app-progress').style.display = 'block';
    document.getElementById('app-scoring-placeholder').style.display = 'none';

    // Show STOP button
    updateStopButtonVisibility(true);

    // Reset stats
    resetAppStats();

    const appType = document.getElementById('app-type').value;
    console.log(`[AUDIT] Starting app audit: ${appType}`);

    try {
        const response = await fetch('/api/v2/app/audit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(getAppConfig())
        });

        if (!response.ok) throw new Error(await response.text());

        const { session_id } = await response.json();
        state.app.sessionId = session_id;

        // Connect to SSE
        connectAppSSE(session_id);

    } catch (err) {
        alert('Error starting app audit: ' + err.message);
        btn.disabled = false;
        btn.textContent = 'Start App Audit';
    }
}

function connectAppSSE(sessionId) {
    const eventSource = new EventSource(`/api/v2/app/progress/${sessionId}`);
    state.app.eventSource = eventSource;

    eventSource.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        updateAppProgress(data);
    });

    eventSource.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data);
        eventSource.close();
        onAppComplete(data);
    });

    eventSource.addEventListener('error', (e) => {
        eventSource.close();
        onAppError(e);
    });

    eventSource.onerror = () => {
        eventSource.close();
        onAppError(new Error('SSE connection lost'));
    };
}

function updateAppProgress(data) {
    if (data.stats) {
        updateAppStats(data.stats);
    }
}

function updateAppStats(stats) {
    document.getElementById('app-entities-count').textContent =
        stats.total_entities ?? 'En cours...';
    document.getElementById('app-records-count').textContent =
        stats.total_records ?? '0';
    document.getElementById('app-pii-count').textContent =
        stats.total_pii_values ?? '0';
    document.getElementById('app-risk-entity').textContent =
        stats.highest_risk_entity ?? '-';
    document.getElementById('app-iban-count').textContent =
        stats.iban_count ?? '0';
}

function resetAppStats() {
    document.getElementById('app-entities-count').textContent = '-';
    document.getElementById('app-records-count').textContent = '-';
    document.getElementById('app-pii-count').textContent = '-';
    document.getElementById('app-risk-entity').textContent = '-';
    document.getElementById('app-iban-count').textContent = '-';
}

function onAppComplete(data) {
    state.app.results = data.result || data;

    const btn = document.getElementById('app-start-btn');
    btn.disabled = false;
    btn.textContent = 'Start App Audit';

    document.getElementById('app-progress').style.display = 'none';

    // Hide STOP button
    updateStopButtonVisibility(false);

    if (data.stats) {
        updateAppStats(data.stats);
    }

    // Show export button
    document.getElementById('app-export-btn').style.display = 'block';

    // Show scoring placeholder
    document.getElementById('app-scoring-placeholder').style.display = 'block';

    // Display errors if any
    if (state.app.sessionId) {
        displayErrors(state.app.sessionId, 'app');
    }

    if (data.status === 'complete') {
        showStatus('App audit complete! Check Hub Dashboard for scores.', 'success');
    } else if (data.error) {
        showStatus('App audit error: ' + data.error, 'error');
    }

    console.log('[AUDIT] App complete:', data);
}

function onAppError(err) {
    console.error('App SSE error:', err);
    const btn = document.getElementById('app-start-btn');
    btn.disabled = false;
    btn.textContent = 'Start App Audit';
    document.getElementById('app-progress').style.display = 'none';
    updateStopButtonVisibility(false);
    showStatus('App Audit error. Check console for details.', 'error');
}

function exportAppReport() {
    if (!state.app.results) {
        alert('No app audit results to export');
        return;
    }
    const timestamp = new Date().toISOString().split('T')[0];
    downloadJson(state.app.results, `APOLLO_app_audit_${timestamp}.json`);
}

// ============================================================================
// INIT
// ============================================================================

console.log('[APOLLO] Agent Cloud V1.7.R initialized');
console.log('[APOLLO] Mode: Cloud (scoring on Hub)');
