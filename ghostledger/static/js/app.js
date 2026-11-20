/**
 * GhostLedger AI - Frontend Application Controller
 * Handles CSRF tokens, modal interactions, seed-data triggers, and reactive UI.
 */

document.addEventListener('DOMContentLoaded', () => {
    initModals();
    initFlashAutoDismiss();
    initDemoSeeder();
});

// CSRF Token Helper
function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    const input = document.querySelector('input[name="csrf_token"]');
    if (input) return input.value;
    return '';
}

// Modal System
function initModals() {
    document.querySelectorAll('[data-modal-target]').forEach(trigger => {
        trigger.addEventListener('click', (e) => {
            e.preventDefault();
            const targetId = trigger.getAttribute('data-modal-target');
            const modal = document.getElementById(targetId);
            if (modal) {
                // Populate modal fields if data attributes provided
                if (trigger.dataset.actionId) {
                    const actionInput = modal.querySelector('input[name="action_id"]');
                    if (actionInput) actionInput.value = trigger.dataset.actionId;
                }
                if (trigger.dataset.exceptionId) {
                    const excInput = modal.querySelector('input[name="exception_id"]');
                    if (excInput) excInput.value = trigger.dataset.exceptionId;
                }
                modal.classList.add('active');
            }
        });
    });

    document.querySelectorAll('.modal-overlay').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal || e.target.closest('[data-modal-close]')) {
                modal.classList.remove('active');
            }
        });
    });
}

// Auto-dismiss Flash Alerts after 5s
function initFlashAutoDismiss() {
    const flashes = document.querySelectorAll('.flash-message');
    flashes.forEach(flash => {
        setTimeout(() => {
            flash.style.opacity = '0';
            flash.style.transform = 'translateY(-10px)';
            flash.style.transition = 'all 0.3s ease';
            setTimeout(() => flash.remove(), 300);
        }, 6000);
    });
}

// Demo Dataset Seeder Button
function initDemoSeeder() {
    const btn = document.getElementById('btn-seed-demo');
    if (!btn) return;

    btn.addEventListener('click', async (e) => {
        e.preventDefault();
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner"></span> Seeding 100+ Records...`;

        try {
            const resp = await fetch('/api/seed-demo', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                }
            });
            const data = await resp.json();
            if (resp.ok) {
                alert(`Success: ${data.summary}\nYou can now click 'Run Reconciliation' to test the engine!`);
                window.location.reload();
            } else {
                alert(`Error seeding demo data: ${data.error || 'Server error'}`);
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        } catch (err) {
            alert(`Network failure: ${err.message}`);
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    });
}
