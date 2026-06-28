/* ═══════════════════════════════════════════════════
   main.js — 全局共用功能
   Toast 通知、導航、通用輔助函數
   ═══════════════════════════════════════════════════ */

// ── Toast 通知 ──────────────────────────────────
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    container.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:1000;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(container);
    return container;
}

// ── 導航 ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const navToggle = document.getElementById('navToggle');
    const navLinks = document.getElementById('navLinks');

    if (navToggle && navLinks) {
        navToggle.addEventListener('click', () => {
            navLinks.classList.toggle('open');
        });
    }

    navLinks?.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
            navLinks.classList.remove('open');
        });
    });

    // Language switcher dropdown
    const langToggle = document.getElementById('langToggle');
    const langDropdown = document.getElementById('langDropdown');

    if (langToggle && langDropdown) {
        langToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            langDropdown.classList.toggle('show');
        });

        document.addEventListener('click', () => {
            langDropdown.classList.remove('show');
        });
    }
});

// ── Flash message display ───────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Check for hidden flash data passed via meta tags or data attributes
    const flashContainer = document.getElementById('flash-data');
    if (flashContainer) {
        try {
            const flashes = JSON.parse(flashContainer.textContent);
            flashes.forEach(([category, message]) => showToast(message, category));
        } catch (e) {}
    }
});

// ── API helper ──────────────────────────────────
async function apiFetch(url, options = {}) {
    try {
        const res = await fetch(url, options);
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || `HTTP ${res.status}`);
        }
        return data;
    } catch (e) {
        showToast(e.message, 'error');
        throw e;
    }
}

// ── File upload helper ──────────────────────────
function setupUploadZone(zoneId, inputId, onFileSelected, acceptTypes = '*') {
    const zone = document.getElementById(zoneId);
    const input = document.getElementById(inputId);

    if (!zone || !input) return;

    zone.addEventListener('click', () => input.click());

    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
    });

    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0 && onFileSelected) {
            onFileSelected(files[0]);
        }
    });

    input.addEventListener('change', () => {
        if (input.files.length > 0 && onFileSelected) {
            onFileSelected(input.files[0]);
        }
    });
}

// ── Format file size ────────────────────────────
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
}