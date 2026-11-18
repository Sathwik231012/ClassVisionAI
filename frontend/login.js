/* ══════════════════════════════════════════════════════════════════════════
   ClassVisionAI — Login Page JavaScript
   ══════════════════════════════════════════════════════════════════════════ */

'use strict';

// Toggle password visibility
function togglePassword() {
  const passwordInput = document.getElementById('password');
  const type = passwordInput.type === 'password' ? 'text' : 'password';
  passwordInput.type = type;
}

// Handle login form submission
function handleLogin(event) {
  event.preventDefault();
  
  const username = document.getElementById('username').value;
  const password = document.getElementById('password').value;
  const remember = document.getElementById('remember').checked;
  
  // Simple demo authentication (no backend for now)
  if (username === 'teacher' && password === 'demo123') {
    // Store session
    if (remember) {
      localStorage.setItem('classvision_user', username);
    } else {
      sessionStorage.setItem('classvision_user', username);
    }
    
    // Show success and redirect
    showToast('Login successful! Redirecting...', 'success');
    setTimeout(() => {
      window.location.href = '/app';
    }, 1000);
  } else {
    showToast('Invalid credentials. Try: teacher / demo123', 'error');
  }
}

// Simple toast notification
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    top: 24px;
    right: 24px;
    padding: 16px 24px;
    background: ${type === 'success' ? '#22C55E' : '#EF4444'};
    color: white;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    font-weight: 500;
    z-index: 9999;
    animation: slideIn 0.3s ease;
  `;
  
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
  @keyframes slideIn {
    from {
      transform: translateX(400px);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }
  
  @keyframes slideOut {
    from {
      transform: translateX(0);
      opacity: 1;
    }
    to {
      transform: translateX(400px);
      opacity: 0;
    }
  }
`;
document.head.appendChild(style);

// Auto-fill demo credentials on page load (for convenience)
window.addEventListener('DOMContentLoaded', () => {
  // Check if already logged in
  const user = localStorage.getItem('classvision_user') || sessionStorage.getItem('classvision_user');
  if (user) {
    window.location.href = '/app';
  }
});
