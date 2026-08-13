(function () {
  var $ = function (id) { return document.getElementById(id); };
  var next = window.__TGM_LOGIN_NEXT__ || '/chat';

  function showError(msg) {
    var el = $('loginError');
    el.textContent = msg;
    el.style.display = 'block';
  }
  function clearError() {
    $('loginError').style.display = 'none';
  }

  function requestOtp() {
    var email = $('loginEmail').value.trim();
    if (!email || email.indexOf('@') === -1) {
      showError('Enter a valid email address.');
      return;
    }
    clearError();
    var btn = $('requestOtpBtn');
    btn.disabled = true;
    btn.textContent = 'Sending…';

    fetch('/api/auth/request-otp', {
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
      $('stepCode').style.display = 'block';
      $('loginCode').focus();
    }).catch(function () {
      btn.disabled = false;
      btn.textContent = 'Send me a code →';
      showError('Could not reach the server — check your connection and try again.');
    });
  }

  function verifyOtp() {
    var email = $('loginEmail').value.trim();
    var code = $('loginCode').value.trim();
    if (!code) {
      showError('Enter the 6-digit code.');
      return;
    }
    clearError();
    var btn = $('verifyOtpBtn');
    btn.disabled = true;
    btn.textContent = 'Verifying…';

    fetch('/api/auth/verify-otp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email, code: code, next: next })
    }).then(function (res) {
      return res.json().then(function (data) { return { ok: res.ok, data: data }; });
    }).then(function (result) {
      if (!result.ok) {
        btn.disabled = false;
        btn.textContent = 'Verify & continue →';
        showError((result.data && result.data.error) || 'Incorrect code — try again.');
        return;
      }
      window.location.href = result.data.redirect || next;
    }).catch(function () {
      btn.disabled = false;
      btn.textContent = 'Verify & continue →';
      showError('Could not reach the server — check your connection and try again.');
    });
  }

  $('requestOtpBtn').addEventListener('click', requestOtp);
  $('verifyOtpBtn').addEventListener('click', verifyOtp);
  $('resendOtpBtn').addEventListener('click', requestOtp);

  if ($('loginEmail').value.trim()) {
    // Email was pre-filled (came from the ROI calculator's "returning email"
    // redirect) -- kick off the OTP request immediately so the student
    // doesn't have to re-type/confirm their own email.
    requestOtp();
  }
})();
