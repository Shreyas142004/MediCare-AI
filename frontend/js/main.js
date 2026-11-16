/**
 * MediCare AI - Main UI Controller
 * Handles Navigation state, Authentication UI synchronization, and Global utilities
 */

document.addEventListener('DOMContentLoaded', () => {
  initNavbar();
  checkAuthAndRedirect();
  initFooterYear();
});

/**
 * Initializes navbar authentication state and mobile toggling
 */
function initNavbar() {
  const navContainer = document.querySelector('.navbar .nav-container');
  if (!navContainer) return;

  const auth = window.api ? window.api.isAuthenticated() : false;
  const user = window.api ? window.api.getUser() : null;
  const currentPath = window.location.pathname.split('/').pop() || 'index.html';

  // Highlight active link
  document.querySelectorAll('.nav-link').forEach(link => {
    const href = link.getAttribute('href');
    if (href === currentPath || (currentPath === '' && href === 'index.html')) {
      link.classList.add('active');
    } else {
      link.classList.remove('active');
    }
  });

  // Mobile menu toggle
  const toggleBtn = document.querySelector('.nav-toggle');
  const navLinks = document.querySelector('.nav-links');
  if (toggleBtn && navLinks) {
    toggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      navLinks.classList.toggle('open');
      const isOpen = navLinks.classList.contains('open');
      toggleBtn.setAttribute('aria-expanded', isOpen);
      toggleBtn.innerHTML = isOpen ? '✕' : '☰';
    });

    document.querySelectorAll('.nav-link').forEach(link => {
      link.addEventListener('click', () => {
        navLinks.classList.remove('open');
        if (toggleBtn) {
          toggleBtn.setAttribute('aria-expanded', 'false');
          toggleBtn.innerHTML = '☰';
        }
      });
    });

    document.addEventListener('click', (e) => {
      if (navContainer && !navContainer.contains(e.target)) {
        navLinks.classList.remove('open');
        if (toggleBtn) {
          toggleBtn.setAttribute('aria-expanded', 'false');
          toggleBtn.innerHTML = '☰';
        }
      }
    });
  }

  // Update actions container
  const navActions = document.querySelector('.nav-actions');
  if (navActions) {
    if (auth && user) {
      const displayName = user.full_name ? user.full_name.split(' ')[0] : 'User';
      navActions.innerHTML = `
        <div class="user-menu" id="user-menu">
          <button class="user-badge-btn" id="user-dropdown-btn">
            <span style="font-size:1.1rem">👤</span>
            <span>${displayName}</span>
            <span style="font-size:0.75rem; margin-left:2px;">▼</span>
          </button>
          <div class="user-dropdown" id="user-dropdown-menu">
            <div style="padding: 0.5rem 1rem; font-size: 0.8rem; color: var(--text-muted); border-bottom: 1px solid var(--border-light);">
              Signed in as<br><strong style="color: var(--text-main); font-size: 0.85rem;">${user.email}</strong>
            </div>
            <a href="dashboard.html">📊 Dashboard</a>
            <a href="scanner.html">🔍 Scan Medicine</a>
            <a href="history.html">📋 Scan History</a>
            <a href="profile.html">⚙ Profile Settings</a>
            <div class="divider"></div>
            <button id="nav-logout-btn" style="color: var(--danger);">🚪 Sign Out</button>
          </div>
        </div>
      `;

      // Dropdown toggle
      const dropBtn = document.getElementById('user-dropdown-btn');
      const dropMenu = document.getElementById('user-dropdown-menu');
      if (dropBtn && dropMenu) {
        dropBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          dropMenu.classList.toggle('show');
        });

        document.addEventListener('click', () => {
          dropMenu.classList.remove('show');
        });
      }

      // Logout handler
      const logoutBtn = document.getElementById('nav-logout-btn');
      if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
          window.api.logout();
        });
      }
    } else {
      navActions.innerHTML = `
        <a href="login.html" class="btn btn-outline btn-sm">Log In</a>
        <a href="register.html" class="btn btn-primary btn-sm nav-signup-btn">Get Started</a>
      `;
    }
  }
}

/**
 * Route protection for pages requiring authentication
 */
function checkAuthAndRedirect() {
  const currentPath = window.location.pathname.split('/').pop() || 'index.html';
  const protectedPages = ['dashboard.html', 'profile.html', 'history.html'];
  const authPages = ['login.html', 'register.html', 'forgot-password.html', 'verify-otp.html', 'reset-password.html'];

  const isAuth = window.api ? window.api.isAuthenticated() : false;

  if (protectedPages.includes(currentPath) && !isAuth) {
    window.location.href = `login.html?redirect=${encodeURIComponent(currentPath)}`;
  }

  if (authPages.includes(currentPath) && isAuth) {
    window.location.href = 'dashboard.html';
  }
}

/**
 * Updates copyright year in footer
 */
function initFooterYear() {
  const yearElem = document.getElementById('current-year');
  if (yearElem) {
    yearElem.textContent = new Date().getFullYear();
  }
}

