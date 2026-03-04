/**
 * Apollo Data Auditor V1.7.R - API Wrapper (Rust Hybrid)
 * Fetch utilities for V2 API endpoints
 * (c) 2025-2026 Gilles Gabriel - gilles.gabriel@noos.fr
 */

const API = {
    BASE_URL: '/api/v2',

    /**
     * Get headers with API key for Hub authentication
     */
    getHeaders() {
        const headers = { 'Content-Type': 'application/json' };
        const apiKey = AUTH.getApiKey();
        if (apiKey) {
            headers['X-API-Key'] = apiKey;
        }
        return headers;
    },

    /**
     * Start Files audit
     * @param {Array<string>} sources - List of file paths
     * @param {Array<string>} excludedSources - Names of excluded sources (opt-out)
     * @returns {Promise<{session_id: string}>}
     */
    async startFilesAudit(sources, excludedSources = []) {
        const response = await fetch(`${this.BASE_URL}/files/audit`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ sources, excluded_sources: excludedSources })
        });
        if (!response.ok) throw new Error(await response.text());
        return response.json();
    },

    /**
     * Start Database audit
     * @param {Array<Object>} sources - List of DB configs {db_type, host, port, database, username, password}
     * @param {Array<string>} excludedSources - Names of excluded databases (opt-out)
     * @returns {Promise<{session_id: string}>}
     */
    async startDbAudit(sources, excludedSources = []) {
        const response = await fetch(`${this.BASE_URL}/databases/audit`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ sources, excluded_sources: excludedSources })
        });
        if (!response.ok) throw new Error(await response.text());
        return response.json();
    },

    /**
     * Get audit results
     * @param {string} type - 'files' or 'databases'
     * @param {string} sessionId
     * @returns {Promise<Object>} - OrchestratorOutput
     */
    async getResults(type, sessionId) {
        const response = await fetch(`${this.BASE_URL}/${type}/results/${sessionId}`);
        if (!response.ok) throw new Error(await response.text());
        return response.json();
    },

    /**
     * Connect to SSE progress stream
     * @param {string} type - 'files' or 'databases'
     * @param {string} sessionId
     * @param {Function} onProgress - Callback for progress events
     * @param {Function} onComplete - Callback when done
     * @param {Function} onError - Callback on error
     * @returns {EventSource}
     */
    streamProgress(type, sessionId, onProgress, onComplete, onError) {
        const eventSource = new EventSource(`${this.BASE_URL}/${type}/progress/${sessionId}`);

        eventSource.addEventListener('progress', (e) => {
            const data = JSON.parse(e.data);
            onProgress(data);
        });

        eventSource.addEventListener('complete', (e) => {
            const data = JSON.parse(e.data);
            eventSource.close();
            onComplete(data);
        });

        eventSource.addEventListener('error', (e) => {
            eventSource.close();
            onError(e);
        });

        eventSource.onerror = () => {
            eventSource.close();
            onError(new Error('SSE connection lost'));
        };

        return eventSource;
    }
};
