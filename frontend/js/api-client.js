/**
 * Client API unifié pour communiquer avec le backend FastAPI
 */

// URL relative : l'API est servie sur la même origine via le reverse proxy nginx
// (/api -> backend). Évite tout "mixed content" en HTTPS et fonctionne en HTTP.
const API_BASE_URL = `/api/v1`;

class ApiClient {
    constructor() {
        this.baseUrl = API_BASE_URL;
        this.refreshPromise = null;
    }

    // Récupérer le token d'accès
    getAccessToken() {
        return localStorage.getItem('access_token');
    }

    // Récupérer le refresh token
    getRefreshToken() {
        return localStorage.getItem('refresh_token');
    }

    // Sauvegarder les tokens
    setTokens(accessToken, refreshToken) {
        localStorage.setItem('access_token', accessToken);
        if (refreshToken) {
            localStorage.setItem('refresh_token', refreshToken);
        }
    }

    // Nettoyer les tokens
    clearTokens() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
    }

    // Headers par défaut
    getHeaders(includeAuth = true) {
        const headers = {
            'Content-Type': 'application/json'
        };

        if (includeAuth) {
            const token = this.getAccessToken();
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
        }

        return headers;
    }

    // Rafraîchir le token
    async refreshToken() {
        // Éviter plusieurs rafraîchissements simultanés
        if (this.refreshPromise) {
            return this.refreshPromise;
        }

        this.refreshPromise = (async () => {
            try {
                const refreshToken = this.getRefreshToken();
                if (!refreshToken) {
                    throw new Error('No refresh token');
                }

                const response = await fetch(`${this.baseUrl}/auth/refresh`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh_token: refreshToken })
                });

                if (!response.ok) {
                    throw new Error('Refresh failed');
                }

                const data = await response.json();
                this.setTokens(data.access_token, data.refresh_token);
                return data.access_token;

            } catch (error) {
                this.clearTokens();
                window.location.href = 'login.html';
                throw error;
            } finally {
                this.refreshPromise = null;
            }
        })();

        return this.refreshPromise;
    }

    // Requête HTTP avec gestion automatique du token
    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        let response = await fetch(url, {
            ...options,
            headers: this.getHeaders(options.includeAuth !== false)
        });

        // Si token expiré, rafraîchir et réessayer
        if (response.status === 401 && options.includeAuth !== false) {
            try {
                const newToken = await this.refreshToken();
                const newHeaders = {
                    ...options.headers,
                    'Authorization': `Bearer ${newToken}`,
                    'Content-Type': 'application/json'
                };
                response = await fetch(url, {
                    ...options,
                    headers: newHeaders
                });
            } catch (error) {
                throw new Error('Session expirée, veuillez vous reconnecter');
            }
        }

        // Gérer les erreurs
        if (!response.ok) {
            let errorMessage = `Erreur ${response.status}`;
            try {
                const errorData = await response.json();
                errorMessage = errorData.detail || errorData.message || errorMessage;
            } catch (e) {
                // Ignorer
            }
            throw new Error(errorMessage);
        }

        // Retourner JSON si présent
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return await response.json();
        }

        return response;
    }

    // ============ Méthodes API ============

    // Auth
    async login(username, password) {
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        const response = await fetch(`${this.baseUrl}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Échec de la connexion');
        }

        const data = await response.json();
        this.setTokens(data.access_token, data.refresh_token);
        localStorage.setItem('user', JSON.stringify(data.user));
        return data;
    }

    async register(userData) {
        const response = await fetch(`${this.baseUrl}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(userData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Échec de l\'inscription');
        }

        return await response.json();
    }

    async logout() {
        try {
            await this.request('/auth/logout', { method: 'POST' });
        } catch (e) {
            // Ignorer les erreurs de logout
        }
        this.clearTokens();
        window.location.href = 'login.html';
    }

    async getCurrentUser() {
        return await this.request('/auth/me');
    }

    // Upload
    async uploadFile(file, onProgress) {
        const formData = new FormData();
        formData.append('file', file);

        const token = this.getAccessToken();

        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();

            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable && onProgress) {
                    onProgress(Math.round((e.loaded / e.total) * 100));
                }
            });

            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(JSON.parse(xhr.response));
                } else {
                    try {
                        const error = JSON.parse(xhr.response);
                        reject(new Error(error.detail || 'Upload failed'));
                    } catch {
                        reject(new Error(`Upload failed: ${xhr.status}`));
                    }
                }
            });

            xhr.addEventListener('error', () => reject(new Error('Network error')));
            xhr.addEventListener('abort', () => reject(new Error('Upload cancelled')));

            xhr.open('POST', `${this.baseUrl}/upload/`);
            if (token) {
                xhr.setRequestHeader('Authorization', `Bearer ${token}`);
            }
            xhr.send(formData);
        });
    }

    async analyzeFile(fileId) {
        return await this.request(`/analyze/${fileId}`);
    }

    async getFileInfo(fileId) {
        return await this.request(`/upload/${fileId}`);
    }

    async generateReport(fileId, config) {
        return await this.request(`/generate/${fileId}`, {
            method: 'POST',
            body: JSON.stringify(config)
        });
    }

    async getReportStatus(reportId) {
        return await this.request(`/generate/status/${reportId}`);
    }

    async sendEmail(reportId, emailConfig) {
        return await this.request(`/email/send/${reportId}`, {
            method: 'POST',
            body: JSON.stringify(emailConfig)
        });
    }

    async downloadReport(reportId) {
        const token = this.getAccessToken();
        window.open(`${this.baseUrl}/download/${reportId}?token=${token}`, '_blank');
    }

    // History
    async getHistory(filters = {}) {
        const params = new URLSearchParams(filters).toString();
        const url = params ? `/history?${params}` : '/history';
        return await this.request(url);
    }

    async getFileHistory(fileId) {
        return await this.request(`/history/file/${fileId}`);
    }

    // Admin
    async getSystemStats(days = 30) {
        return await this.request(`/admin/dashboard/stats?days=${days}`);
    }

    async getActivityCharts(days = 30) {
        return await this.request(`/admin/dashboard/charts?days=${days}`);
    }

    async getTopUsers(limit = 10) {
        return await this.request(`/admin/dashboard/top-users?limit=${limit}`);
    }

    async getRecentActivity(limit = 20) {
        return await this.request(`/admin/dashboard/recent-activity?limit=${limit}`);
    }

    async getUsers(filters = {}) {
        const params = new URLSearchParams(filters).toString();
        return await this.request(`/admin/users?${params}`);
    }

    async updateUser(userId, data) {
        return await this.request(`/admin/users/${userId}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    async deleteUser(userId) {
        return await this.request(`/admin/users/${userId}`, {
            method: 'DELETE'
        });
    }

    async getSystemHealth() {
        return await this.request('/admin/system/health');
    }
}

// Instance globale
window.api = new ApiClient();