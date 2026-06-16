/**
 * Gestionnaire d'authentification
 */

class AuthManager {
    constructor() {
        this.user = null;
        this.isInitialized = false;
    }

    async init() {
        if (this.isInitialized) return;

        const token = window.api.getAccessToken();
        if (token) {
            try {
                this.user = await window.api.getCurrentUser();
            } catch (error) {
                console.error('Auth init error:', error);
                this.user = null;
            }
        }

        this.isInitialized = true;
        this.updateUI();
    }

    isAuthenticated() {
        return !!window.api.getAccessToken() && !!this.user;
    }

    isAdmin() {
        return this.user && this.user.is_superuser === true;
    }

    getUser() {
        return this.user;
    }

    async login(username, password) {
        const data = await window.api.login(username, password);
        this.user = data.user;
        this.updateUI();
        return data;
    }

    async logout() {
        await window.api.logout();
        this.user = null;
        this.updateUI();
        window.location.href = 'login.html';
    }

    updateUI() {
        // Mettre à jour les éléments du DOM qui dépendent de l'auth
        const authRequiredElements = document.querySelectorAll('[data-auth-required]');
        const adminElements = document.querySelectorAll('[data-admin-only]');

        const isAuth = this.isAuthenticated();
        const isAdmin = this.isAdmin();

        authRequiredElements.forEach(el => {
            el.style.display = isAuth ? 'block' : 'none';
        });

        adminElements.forEach(el => {
            el.style.display = isAdmin ? 'block' : 'none';
        });

        // Mettre à jour le nom d'utilisateur dans la navbar
        const userMenu = document.getElementById('userMenu');
        if (userMenu && this.user) {
            userMenu.innerHTML = `
                <i class="bi bi-person-circle"></i>
                ${this.user.username}
            `;
        }
    }
}

// Instance globale
window.auth = new AuthManager();