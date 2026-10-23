(function () {
  var $ = function (id) { return document.getElementById(id); };
  var transcript = $('acTranscript');
  if (!transcript) return;
  var studentId = transcript.getAttribute('data-student-id');
  var lastId = parseInt(transcript.getAttribute('data-last-id'), 10) || 0;
  var input = $('acInput');
  var sendBtn = $('acSendBtn');

  function scrollToBottom() { transcript.scrollTop = transcript.scrollHeight; }
  scrollToBottom();

  function appendMessage(senderType, content) {
    var empty = transcript.querySelector('.empty');
    if (empty) empty.remove();
    var div = document.createElement('div');
    div.className = 'ac-bubble ac-' + (senderType === 'student' ? 'user' : 'counsellor');
    div.textContent = content;
    transcript.appendChild(div);
    scrollToBottom();
  }

  function send() {
    var content = input.value.trim();
    if (!content) return;
    input.disabled = true; sendBtn.disabled = true;
    fetch('/api/counselor/chat/' + studentId + '/messages', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: content })
    }).then(function (r) { return r.json(); })
      .then(function (d) {
        input.disabled = false; sendBtn.disabled = false;
        if (!d.ok) return;
        input.value = '';
        appendMessage('counselor', content);
        lastId = Math.max(lastId, d.message_id || 0);
        input.focus();
      }).catch(function () { input.disabled = false; sendBtn.disabled = false; });
  }
  sendBtn.addEventListener('click', send);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });

  function poll() {
    if (document.visibilityState === 'hidden') return;
    fetch('/api/counselor/chat/' + studentId + '/messages?since=' + lastId)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) return;
        d.messages.forEach(function (m) {
          appendMessage(m.sender_type, m.content);
          lastId = Math.max(lastId, m.id);
        });
      }).catch(function () {});
  }
  setInterval(poll, 4000);
})();
