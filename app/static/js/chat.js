(function () {
  var $ = function (id) { return document.getElementById(id); };
  var windowEl = $('chatWindow');
  var input = $('chatInput');
  var sendBtn = $('chatSendBtn');
  var errorEl = $('chatError');

  var lastId = parseInt(windowEl.getAttribute('data-last-id'), 10) || 0;
  var currentMode = window.__TGM_CHAT_MODE__ || 'ai';

  function scrollToBottom() {
    windowEl.scrollTop = windowEl.scrollHeight;
  }

  // Server-rendered message history (chat.html's {% for m in messages %})
  // is plain escaped text, same as appendBubble used to insert before this
  // fix -- reprocess it through the same markdown renderer so history and
  // newly-sent messages format consistently. .textContent here reads back
  // the original decoded text regardless of how it was inserted, so this
  // is safe to re-run through escapeHtml() inside renderChatMarkdown.
  Array.prototype.forEach.call(windowEl.querySelectorAll('.chat-bubble'), function (el) {
    el.innerHTML = renderChatMarkdown(el.textContent);
  });

  scrollToBottom();

  // role: 'user' | 'model' | 'counsellor' | 'system'. System notices (e.g.
  // "a counsellor has been notified") render as a centered pill, not a
  // bubble -- they're not part of the back-and-forth, just a status update.
  function appendMessage(role, content) {
    var div = document.createElement('div');
    if (role === 'system') {
      div.className = 'chat-system';
      div.textContent = content;
    } else {
      div.className = 'chat-bubble chat-' + role;
      div.innerHTML = renderChatMarkdown(content);
    }
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

  // A slow Amara reply (up to 90s) can arrive after the 4s poll loop has
  // already picked up and rendered the same saved message -- guard against
  // rendering it a second time from the direct /api/chat(/opening) response.
  function renderReplyIfNew(text, id) {
    if (!id || id > lastId) appendMessage('model', text);
    if (id) lastId = Math.max(lastId, id);
  }

  function send() {
    var message = input.value.trim();
    if (!message) return;
    clearError();
    input.value = '';
    input.disabled = true;
    sendBtn.disabled = true;

    appendMessage('user', message);
    // A human who's already taken this conversation over is who'll answer --
    // showing "Amara is typing" would be a lie in that mode, so skip it.
    var thinkingBubble = currentMode === 'ai' ? appendMessage('model', 'Amara is typing…') : null;
    if (thinkingBubble) thinkingBubble.classList.add('chat-thinking');

    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: message })
    }).then(function (res) {
      return res.json().then(function (data) { return { ok: res.ok, data: data }; });
    }).then(function (result) {
      if (thinkingBubble) thinkingBubble.remove();
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
      if (!result.ok) {
        showError((result.data && result.data.error) || 'Something went wrong — try again.');
        return;
      }
      if (result.data.user_message_id) lastId = Math.max(lastId, result.data.user_message_id);
      if (result.data.mode) currentMode = result.data.mode;
      if (result.data.reply) renderReplyIfNew(result.data.reply, result.data.reply_message_id);
      // mode === 'human' with no reply: the message is sent and waiting on
      // a counsellor -- poll() below picks up their answer when it arrives.
    }).catch(function () {
      if (thinkingBubble) thinkingBubble.remove();
      input.disabled = false;
      sendBtn.disabled = false;
      showError('Could not reach the server — check your connection and try again.');
    });
  }

  function fetchOpening() {
    var thinkingBubble = appendMessage('model', "Amara is putting together your personalised welcome…");
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
          var retryBubble = appendMessage(
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
        renderReplyIfNew(result.data.reply, result.data.reply_message_id);
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

  // ---------- polling ----------
  // Picks up anything that shows up in this chat without the student
  // asking for it -- a counsellor's live reply, or a system notice (e.g.
  // "a counsellor has been notified"). Mirrors the same setInterval-poll
  // pattern community.js already uses for room posts.
  function poll() {
    if (document.visibilityState === 'hidden') return;
    fetch('/api/chat/poll?since=' + lastId)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) return;
        if (d.mode) currentMode = d.mode;
        d.messages.forEach(function (m) {
          appendMessage(m.role, m.content);
          lastId = Math.max(lastId, m.id);
        });
      })
      .catch(function () {});
  }
  setInterval(poll, 4000);
})();
