/**
 * MediCare AI - Authentication & Profile Controller
 * Manages form submissions, validation, OTP verification, and password workflows
 */

document.addEventListener('DOMContentLoaded', () => {
  initRegisterForm();
  initLoginForm();
  initForgotPasswordForm();
  initVerifyOtpForm();
  initResetPasswordForm();
  initProfilePage();
});

/**
 * Registration Page Handler
 */
function initRegisterForm() {
  const form = document.getElementById('register-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type="submit"]');
    const fullName = document.getElementById('full_name').value.trim();
    const email = document.getElementById('email').value.trim();
    const phone = document.getElementById('phone')?.value.trim() || null;
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirm_password').value;

    if (password.length < 6) {
      showToast('Password must be at least 6 characters long.', 'error');
      return;
    }

    if (password !== confirmPassword) {
      showToast('Passwords do not match. Please recheck.', 'error');
      return;
    }

    try {
      btn.disabled = true;
      btn.textContent = 'Creating Account...';
      const res = await window.api.register(fullName, email, password, phone);
      showToast('Account registered successfully! Welcome to MediCare AI.', 'success');
      setTimeout(() => {
        window.location.href = 'dashboard.html';
      }, 1000);
    } catch (err) {
      showToast(err.message || 'Registration failed. Please try again.', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Create Free Account';
    }
  });
}

/**
 * Login Page Handler
 */
function initLoginForm() {
  const form = document.getElementById('login-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type="submit"]');
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    try {
      btn.disabled = true;
      btn.textContent = 'Authenticating...';
      await window.api.login(email, password);
      showToast('Signed in successfully!', 'success');
      
      const urlParams = new URLSearchParams(window.location.search);
      const redirect = urlParams.get('redirect') || 'dashboard.html';
      setTimeout(() => {
        window.location.href = redirect;
      }, 800);
    } catch (err) {
      showToast(err.message || 'Invalid email or password.', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Sign In';
    }
  });
}

/**
 * Forgot Password Page Handler
 */
function initForgotPasswordForm() {
  const form = document.getElementById('forgot-password-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type="submit"]');
    const email = document.getElementById('email').value.trim();

    try {
      btn.disabled = true;
      btn.textContent = 'Generating OTP...';
      const res = await window.api.forgotPassword(email);
      showToast(res.message || 'Verification code generated.', 'success');
      
      sessionStorage.setItem('medicare_reset_email', email);
      if (res.demo_otp) {
        sessionStorage.setItem('medicare_demo_otp', res.demo_otp);
      }

      setTimeout(() => {
        window.location.href = `verify-otp.html?email=${encodeURIComponent(email)}`;
      }, 1200);
    } catch (err) {
      showToast(err.message || 'Failed to request password reset.', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Send Verification Code';
    }
  });
}

/**
 * Verify OTP Page Handler
 */
function initVerifyOtpForm() {
  const form = document.getElementById('verify-otp-form');
  if (!form) return;

  const urlParams = new URLSearchParams(window.location.search);
  const emailParam = urlParams.get('email') || sessionStorage.getItem('medicare_reset_email') || '';
  const emailInput = document.getElementById('email');
  if (emailInput && emailParam) {
    emailInput.value = emailParam;
  }

  // Pre-fill demo OTP hint if available in development
  const demoOtp = sessionStorage.getItem('medicare_demo_otp');
  const demoHint = document.getElementById('demo-otp-hint');
  if (demoHint && demoOtp) {
    demoHint.innerHTML = `<em>Demo Environment OTP: <strong>${demoOtp}</strong></em>`;
    demoHint.style.display = 'block';
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type="submit"]');
    const email = document.getElementById('email').value.trim();
    const otp = document.getElementById('otp').value.trim();

    try {
      btn.disabled = true;
      btn.textContent = 'Verifying...';
      await window.api.verifyOtp(email, otp);
      showToast('OTP verified! Please set your new password.', 'success');
      
      sessionStorage.setItem('medicare_verified_otp', otp);
      setTimeout(() => {
        window.location.href = `reset-password.html?email=${encodeURIComponent(email)}&otp=${encodeURIComponent(otp)}`;
      }, 1000);
    } catch (err) {
      showToast(err.message || 'Invalid or expired OTP code.', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Verify Code';
    }
  });
}

/**
 * Reset Password Page Handler
 */
function initResetPasswordForm() {
  const form = document.getElementById('reset-password-form');
  if (!form) return;

  const urlParams = new URLSearchParams(window.location.search);
  const emailParam = urlParams.get('email') || sessionStorage.getItem('medicare_reset_email') || '';
  const otpParam = urlParams.get('otp') || sessionStorage.getItem('medicare_verified_otp') || '';

  const emailInput = document.getElementById('email');
  const otpInput = document.getElementById('otp');
  if (emailInput && emailParam) emailInput.value = emailParam;
  if (otpInput && otpParam) otpInput.value = otpParam;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button[type="submit"]');
    const email = document.getElementById('email').value.trim();
    const otp = document.getElementById('otp').value.trim();
    const newPassword = document.getElementById('new_password').value;
    const confirmPassword = document.getElementById('confirm_password').value;

    if (newPassword.length < 6) {
      showToast('New password must be at least 6 characters long.', 'error');
      return;
    }

    if (newPassword !== confirmPassword) {
      showToast('Passwords do not match.', 'error');
      return;
    }

    try {
      btn.disabled = true;
      btn.textContent = 'Updating Password...';
      await window.api.resetPassword(email, otp, newPassword);
      showToast('Password reset successfully! Please sign in.', 'success');
      
      sessionStorage.removeItem('medicare_reset_email');
      sessionStorage.removeItem('medicare_demo_otp');
      sessionStorage.removeItem('medicare_verified_otp');

      setTimeout(() => {
        window.location.href = 'login.html';
      }, 1200);
    } catch (err) {
      showToast(err.message || 'Failed to reset password.', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Reset Password';
    }
  });
}

/**
 * Profile Settings Page Handler
 */
async function initProfilePage() {
  const profileForm = document.getElementById('profile-form');
  const passwordForm = document.getElementById('change-password-form');
  if (!profileForm) return;

  try {
    const user = await window.api.getProfile();
    document.getElementById('profile-name').value = user.full_name || '';
    document.getElementById('profile-email').value = user.email || '';
    document.getElementById('profile-phone').value = user.phone || '';
    document.getElementById('profile-notes').value = user.medical_notes || '';
    document.getElementById('profile-allergies').value = user.allergies || '';
    
    const bannerName = document.getElementById('profile-display-name');
    if (bannerName) bannerName.textContent = user.full_name;
    const bannerEmail = document.getElementById('profile-display-email');
    if (bannerEmail) bannerEmail.textContent = user.email;
  } catch (err) {
    showToast('Failed to load profile details.', 'error');
  }

  // Profile update submit
  profileForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = profileForm.querySelector('button[type="submit"]');
    const updates = {
      full_name: document.getElementById('profile-name').value.trim(),
      phone: document.getElementById('profile-phone').value.trim(),
      medical_notes: document.getElementById('profile-notes').value.trim(),
      allergies: document.getElementById('profile-allergies').value.trim()
    };

    try {
      btn.disabled = true;
      btn.textContent = 'Saving Changes...';
      const updated = await window.api.updateProfile(updates);
      showToast('Profile updated successfully!', 'success');
      
      const bannerName = document.getElementById('profile-display-name');
      if (bannerName) bannerName.textContent = updated.full_name;
    } catch (err) {
      showToast(err.message || 'Failed to update profile.', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Save Profile';
    }
  });

  // Change password submit
  if (passwordForm) {
    passwordForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = passwordForm.querySelector('button[type="submit"]');
      const oldPw = document.getElementById('old_password').value;
      const newPw = document.getElementById('new_password').value;
      const confirmPw = document.getElementById('confirm_new_password').value;

      if (newPw.length < 6) {
        showToast('New password must be at least 6 characters long.', 'error');
        return;
      }
      if (newPw !== confirmPw) {
        showToast('New passwords do not match.', 'error');
        return;
      }

      try {
        btn.disabled = true;
        btn.textContent = 'Changing Password...';
        await window.api.changePassword(oldPw, newPw);
        showToast('Password changed successfully!', 'success');
        passwordForm.reset();
      } catch (err) {
        showToast(err.message || 'Failed to change password.', 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Change Password';
      }
    });
  }
}

