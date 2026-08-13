(function () {
  var $ = function (id) { return document.getElementById(id); };
  var windowEl = $('chatWindow');
  var input = $('chatInput');
  var sendBtn = $('chatSendBtn');
  var errorEl = $('chatError');

  function scrollToBottom() {
    windowEl.scrollTop = windowEl.scrollHeight;
  }
  scrollToBottom();

  function appendBubble(role, content) {
    var div = document.createElement('div');
    div.className = 'chat-bubble chat-' + role;
    div.textContent = content;
    windowEl.appendChild(div);
    scrollToBottom();
    return div;
  }

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.style.display = 'block';
  }
  function clearError() {
    errorEl.style.display = 'none';
  }

  function send() {
    var message = input.value.trim();
    if (!message) return;
    clearError();
    input.value = '';
    input.disabled = true;
    sendBtn.disabled = true;

    appendBubble('user', message);
    var thinkingBubble = appendBubble('model', 'Amara is typing…');
    thinkingBubble.classList.add('chat-thinking');

    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: message })
    }).then(function (res) {
      return res.json().then(function (data) { return { ok: res.ok, data: data }; });
    }).then(function (result) {
      thinkingBubble.remove();
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
      if (!result.ok) {
        showError((result.data && result.data.error) || 'Something went wrong — try again.');
        return;
      }
      appendBubble('model', result.data.reply);
    }).catch(function () {
      thinkingBubble.remove();
      input.disabled = false;
      sendBtn.disabled = false;
      showError('Could not reach the server — check your connection and try again.');
    });
  }

  function fetchOpening() {
    var thinkingBubble = appendBubble('model', "Amara is putting together your personalised welcome…");
    thinkingBubble.classList.add('chat-thinking');
    input.disabled = true;
    sendBtn.disabled = true;

    fetch('/api/chat/opening', { method: 'POST' })
      .then(function (res) {
        return res.json().then(function (data) { return { ok: res.ok, data: data }; });
      }).then(function (result) {
        thinkingBubble.remove();
        input.disabled = false;
        sendBtn.disabled = false;
        if (!result.ok) {
          var retryBubble = appendBubble(
            'model',
            "I'm having trouble connecting right now (" + ((result.data && result.data.error) || 'unknown error') + ")."
          );
          var retryBtn = document.createElement('button');
          retryBtn.textContent = 'Try again';
          retryBtn.className = 'chat-retry-btn';
          retryBtn.addEventListener('click', function () {
            retryBtn.parentNode.remove();
            fetchOpening();
          });
          retryBubble.appendChild(document.createElement('br'));
          retryBubble.appendChild(retryBtn);
          return;
        }
        appendBubble('model', result.data.reply);
        input.focus();
      }).catch(function () {
        thinkingBubble.remove();
        input.disabled = false;
        sendBtn.disabled = false;
        showError('Could not reach the server — check your connection and try again.');
      });
  }

  sendBtn.addEventListener('click', send);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') send();
  });

  if (window.__TGM_NEEDS_OPENING__) {
    fetchOpening();
  } else {
    input.focus();
  }
})();
