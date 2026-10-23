(function () {
  var $ = function (id) { return document.getElementById(id); };
  var next = window.__TGM_RESET_NEXT__ || '/chat';

  function showError(msg) {
    var el = $('resetError');
    el.textContent = msg;
    el.style.display = 'block';
  }
  function clearError() {
    $('resetError').style.display = 'none';
  }

  function requestReset() {
    var email = $('resetEmail').value.trim();
    if (!email || email.indexOf('@') === -1) {
      showError('Enter a valid email address.');
      return;
    }
    clearError();
    var btn = $('requestResetBtn');
    btn.disabled = true;
    btn.textContent = 'Sending…';

    fetch('/api/auth/request-password-reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email })
    }).then(function (res) {
      return res.json().then(function (data) { return { ok: res.ok, data: data }; });
    }).then(function (result) {
      btn.disabled = false;
      btn.textContent = 'Send me a code →';
      if (!result.ok) {
        showError((result.data && result.data.error) || 'Could not send the code — try again.');
        return;
      }
      $('codeEmailLabel').textContent = email;
      $('stepEmail').style.display = 'none';
      $('stepReset').style.display = 'block';
      $('resetCode').focus();
    }).catch(function () {
      btn.disabled = false;
      btn.textContent = 'Send me a code →';
      showError('Could not reach the server — check your connection and try again.');
    });
  }

  function submitReset() {
    var email = $('resetEmail').value.trim();
    var code = $('resetCode').value.trim();
    var newPassword = $('newPassword').value;
    if (!code) {
      showError('Enter the 6-digit code.');
      return;
    }
    if (newPassword.length < 8) {
      showError('New password must be at least 8 characters.');
      return;
    }
    clearError();
    var btn = $('resetPasswordBtn');
    btn.disabled = true;
    btn.textContent = 'Saving…';

    fetch('/api/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email, code: code, new_password: newPassword, next: next })
    }).then(function (res) {
      return res.json().then(function (data) { return { ok: res.ok, data: data }; });
    }).then(function (result) {
      if (!result.ok) {
        btn.disabled = false;
        btn.textContent = 'Set new password →';
        showError((result.data && result.data.error) || 'Could not reset your password — try again.');
        return;
      }
      window.location.href = result.data.redirect || next;
    }).catch(function () {
      btn.disabled = false;
      btn.textContent = 'Set new password →';
      showError('Could not reach the server — check your connection and try again.');
    });
  }

  $('requestResetBtn').addEventListener('click', requestReset);
  $('resetPasswordBtn').addEventListener('click', submitReset);
  $('resendResetBtn').addEventListener('click', requestReset);

  if ($('resetEmail').value.trim()) {
    // Email was pre-filled (came from /login's "This account doesn't have a
    // password yet" message, or the ROI calculator's returning-email
    // redirect) -- kick off the reset request immediately so the student
    // doesn't have to re-type/confirm their own email.
    requestReset();
  }
})();
