(function () {
  var $ = function (id) { return document.getElementById(id); };
  var windowEl = $('chatWindow');
  var input = $('chatInput');
  var sendBtn = $('chatSendBtn');
  var errorEl = $('chatError');

  var counselorId = windowEl.getAttribute('data-counselor-id');
  var lastId = parseInt(windowEl.getAttribute('data-last-id'), 10) || 0;

  function scrollToBottom() { windowEl.scrollTop = windowEl.scrollHeight; }
  scrollToBottom();

  function appendBubble(senderType, content) {
    var system = windowEl.querySelector('.chat-system');
    if (system) system.remove();
    var div = document.createElement('div');
    div.className = 'chat-bubble ' + (senderType === 'student' ? 'chat-user' : 'chat-counsellor');
    div.textContent = content;
    windowEl.appendChild(div);
    scrollToBottom();
  }

  function showError(msg) { errorEl.textContent = msg; errorEl.style.display = 'block'; }
  function clearError() { errorEl.style.display = 'none'; }

  function send() {
    var content = input.value.trim();
    if (!content) return;
    clearError();
    input.value = '';
    input.disabled = true;
    sendBtn.disabled = true;

    appendBubble('student', content);

    fetch('/api/counselors/' + counselorId + '/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: content })
    }).then(function (res) {
      return res.json().then(function (data) { return { ok: res.ok, data: data }; });
    }).then(function (result) {
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
      if (!result.ok || !result.data.ok) {
        showError((result.data && result.data.error) || 'Something went wrong — try again.');
        return;
      }
      if (result.data.message_id) lastId = Math.max(lastId, result.data.message_id);
    }).catch(function () {
      input.disabled = false;
      sendBtn.disabled = false;
      showError('Could not reach the server — check your connection and try again.');
    });
  }

  sendBtn.addEventListener('click', send);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') send();
  });

  function poll() {
    if (document.visibilityState === 'hidden') return;
    fetch('/api/counselors/' + counselorId + '/messages?since=' + lastId)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) return;
        d.messages.forEach(function (m) {
          if (m.id <= lastId) return;
          appendBubble(m.sender_type, m.content);
          lastId = Math.max(lastId, m.id);
        });
      })
      .catch(function () {});
  }
  setInterval(poll, 4000);
})();
