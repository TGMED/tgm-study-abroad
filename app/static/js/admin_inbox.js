(function () {
  var $ = function (id) { return document.getElementById(id); };
  var transcript = $('acTranscript');
  if (!transcript) return;
  var sid = transcript.getAttribute('data-sid');
  var lastId = parseInt(transcript.getAttribute('data-last-id'), 10) || 0;
  var replyBox = $('acReplyBox');
  var input = $('acInput');
  var sendBtn = $('acSendBtn');
  var controls = $('handoffControls');

  function scrollToBottom() { transcript.scrollTop = transcript.scrollHeight; }
  scrollToBottom();

  function appendMessage(role, content) {
    var empty = transcript.querySelector('.empty');
    if (empty) empty.remove();
    var div = document.createElement('div');
    if (role === 'system') {
      div.className = 'ac-system';
      div.textContent = content;
    } else {
      div.className = 'ac-bubble ac-' + role;
      div.textContent = content;
    }
    transcript.appendChild(div);
    scrollToBottom();
  }

  function setButton(mode) {
    controls.innerHTML = '';
    var btn = document.createElement('button');
    btn.className = 'btn btn-green';
    if (mode === 'human') {
      btn.id = 'handbackBtn';
      btn.textContent = '↩️ Hand back to Amara';
      btn.addEventListener('click', handback);
      replyBox.style.display = '';
    } else {
      btn.id = 'takeoverBtn';
      btn.textContent = '🟢 Take over this chat';
      btn.addEventListener('click', takeover);
      replyBox.style.display = 'none';
    }
    controls.appendChild(btn);
  }

  function takeover() {
    fetch('/admin/inbox/' + sid + '/takeover', { method: 'POST' })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d.ok) setButton('human'); });
  }

  function handback() {
    fetch('/admin/inbox/' + sid + '/handback', { method: 'POST' })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d.ok) setButton('ai'); });
  }

  var existingTakeover = $('takeoverBtn'), existingHandback = $('handbackBtn');
  if (existingTakeover) existingTakeover.addEventListener('click', takeover);
  if (existingHandback) existingHandback.addEventListener('click', handback);

  function send() {
    var content = input.value.trim();
    if (!content) return;
    input.disabled = true; sendBtn.disabled = true;
    fetch('/admin/inbox/' + sid + '/reply', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: content })
    }).then(function (r) { return r.json(); })
      .then(function (d) {
        input.disabled = false; sendBtn.disabled = false;
        if (!d.ok) return;
        input.value = '';
        if (!d.id || d.id > lastId) appendMessage('counsellor', content);
        lastId = Math.max(lastId, d.id || 0);
        input.focus();
      }).catch(function () { input.disabled = false; sendBtn.disabled = false; });
  }
  sendBtn.addEventListener('click', send);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });

  // Picks up the student's new messages live (and stays in sync if this
  // conversation is taken over/handed back from another admin tab).
  function poll() {
    if (document.visibilityState === 'hidden') return;
    fetch('/admin/inbox/' + sid + '/poll?since=' + lastId)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) return;
        d.messages.forEach(function (m) {
          appendMessage(m.role, m.content);
          lastId = Math.max(lastId, m.id);
        });
      }).catch(function () {});
  }
  setInterval(poll, 4000);
})();
