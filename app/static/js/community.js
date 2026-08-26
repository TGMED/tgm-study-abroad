(function () {
  var $ = function (id) { return document.getElementById(id); };
  var threadList = $('threadList');
  var room = threadList.getAttribute('data-room');
  var lastId = parseInt(threadList.getAttribute('data-last-id'), 10) || 0;
  var postInput = $('postInput');
  var replyToId = $('replyToId');
  var replyContext = $('replyContext');

  var STAR = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" style="width:60%;height:60%;"><path d="M12 3l2.1 4.7L19 9l-3.6 3.3.9 4.9L12 15l-4.3 2.2.9-4.9L5 9l4.9-1.3z"/></svg>';
  function toast(m, ok) { if (window.tgmToast) window.tgmToast(m, ok); else if (ok === false) alert(m); }
  var SHARE_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/></svg>';

  // ---------- relative time ----------
  function relativeTime(iso) {
    if (!iso) return '';
    var t = Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z');
    if (isNaN(t)) return iso;
    var s = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (s < 45) return 'just now';
    var m = Math.round(s / 60); if (m < 60) return m + 'm ago';
    var h = Math.round(m / 60); if (h < 24) return h + 'h ago';
    var d = Math.round(h / 24); if (d < 7) return d + 'd ago';
    return new Date(t).toLocaleDateString();
  }
  function refreshTimes() {
    threadList.querySelectorAll('.post-time[data-iso]').forEach(function (el) {
      el.textContent = relativeTime(el.getAttribute('data-iso'));
    });
  }

  // ---------- avatar ----------
  function buildAvatar(post, size) {
    var span = document.createElement('span');
    span.className = 'avatar ' + (post.is_ai ? 'ai' : 'av-c' + ((post.author_id || 0) % 5));
    span.style.cssText = 'width:' + size + 'px;height:' + size + 'px;font-size:' + Math.round(size * 0.4) + 'px;';
    if (post.is_ai) span.innerHTML = STAR;
    else if (post.has_avatar) { var img = document.createElement('img'); img.src = '/media/avatar/' + post.author_id; span.appendChild(img); }
    else span.textContent = post.initials || '?';
    // Non-AI avatars link to the author's profile.
    if (!post.is_ai && post.author_id) {
      var link = document.createElement('a');
      link.className = 'pa-link'; link.href = '/u/' + post.author_id; link.title = 'View profile';
      link.appendChild(span);
      return link;
    }
    return span;
  }

  function buildPostCard(post, isReply) {
    var card = document.createElement('div');
    card.className = 'card post-card' + (isReply ? ' post-reply' : '');
    card.setAttribute('data-post-id', post.id);
    card.id = 'post-' + post.id;

    var head = document.createElement('div'); head.className = 'post-head';
    head.appendChild(buildAvatar(post, isReply ? 32 : 40));

    var meta = document.createElement('div'); meta.className = 'ph-meta';
    var author = document.createElement('span');
    author.className = 'post-author' + (post.is_ai ? ' post-author-ai' : '');
    author.textContent = post.author_label; meta.appendChild(author);
    var time = document.createElement('span');
    time.className = 'post-time'; time.setAttribute('data-iso', post.created_at);
    time.textContent = relativeTime(post.created_at); meta.appendChild(time);
    head.appendChild(meta);

    var actions = document.createElement('div'); actions.className = 'ph-actions';
    var share = document.createElement('button');
    share.className = 'post-share'; share.setAttribute('data-post-id', post.id);
    share.title = 'Share'; share.innerHTML = SHARE_ICON; actions.appendChild(share);
    if (!post.is_ai) {
      var rep = document.createElement('button');
      rep.className = 'post-report'; rep.setAttribute('data-post-id', post.id);
      rep.textContent = 'Report'; actions.appendChild(rep);
    }
    head.appendChild(actions);
    card.appendChild(head);

    var content = document.createElement('div'); content.className = 'post-content';
    content.textContent = post.content; card.appendChild(content);

    if (!isReply) {
      var replies = document.createElement('div'); replies.className = 'post-replies';
      card.appendChild(replies);
      var rbtn = document.createElement('button');
      rbtn.className = 'post-reply-btn'; rbtn.setAttribute('data-post-id', post.id);
      rbtn.textContent = 'Reply'; card.appendChild(rbtn);
    }
    return card;
  }

  function addPostToDom(post) {
    if (post.id > lastId) lastId = post.id;
    threadList.setAttribute('data-last-id', String(lastId));
    var empty = threadList.querySelector('.empty'); if (empty) empty.remove();

    if (!post.parent_id) { threadList.appendChild(buildPostCard(post, false)); return; }
    var parent = threadList.querySelector('[data-post-id="' + post.parent_id + '"]');
    if (parent) {
      var rd = parent.querySelector('.post-replies');
      if (rd) { rd.appendChild(buildPostCard(post, true)); return; }
    }
    threadList.appendChild(buildPostCard(post, false));
  }

  // ---------- posting ----------
  function setReplyTarget(postId) {
    replyToId.value = postId || '';
    if (postId) {
      replyContext.style.display = 'block';
      replyContext.textContent = 'Replying to post #' + postId + ' — ';
      var b = document.createElement('button');
      b.textContent = 'cancel';
      b.style.cssText = 'background:none;border:none;color:var(--g-600);text-decoration:underline;cursor:pointer;';
      b.addEventListener('click', function () { setReplyTarget(null); });
      replyContext.appendChild(b);
      postInput.focus();
    } else { replyContext.style.display = 'none'; replyContext.textContent = ''; }
  }

  function submitPost() {
    var content = postInput.value.trim(); if (!content) return;
    var btn = $('postSendBtn'); btn.disabled = true;
    fetch('/api/community/' + room + '/posts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: content, parent_id: replyToId.value || null })
    }).then(function (res) { return res.json().then(function (d) { return { ok: res.ok, d: d }; }); })
      .then(function (r) {
        btn.disabled = false;
        if (!r.ok) { toast((r.d && r.d.error) || 'Could not post.', false); return; }
        postInput.value = ''; setReplyTarget(null);
        addPostToDom(r.d.post);
        if (r.d.ai_reply) addPostToDom(r.d.ai_reply);
        toast('Posted');
      }).catch(function () { btn.disabled = false; toast('Could not reach the server — try again.', false); });
  }

  function reportPost(postId) {
    var reason = window.prompt('Why are you reporting this post? (optional)') || '';
    fetch('/api/community/posts/' + postId + '/report', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d.ok) toast('Report submitted — thank you');
    });
  }

  // ---------- share ----------
  var shareModal = $('shareModal'), sharePreview = $('sharePreview'), shareUrl = $('shareUrl');
  var shareContacts = $('shareContacts'), shareContactSearch = $('shareContactSearch');
  var currentShareId = null;

  function openShare(postId) {
    currentShareId = postId;
    var card = threadList.querySelector('[data-post-id="' + postId + '"]');
    var author = card ? (card.querySelector('.post-author') || {}).textContent : '';
    var text = card ? (card.querySelector('.post-content') || {}).textContent : '';
    sharePreview.innerHTML = '';
    var pv = document.createElement('div');
    pv.innerHTML = '<b></b><p></p>';
    pv.querySelector('b').textContent = author || 'Post';
    pv.querySelector('p').textContent = (text || '').slice(0, 160);
    sharePreview.appendChild(pv);
    shareUrl.value = location.origin + '/community/' + room + '?post=' + postId;
    shareModal.classList.add('show');
    if (shareContacts) loadContacts('');
  }
  function closeShare() { shareModal.classList.remove('show'); currentShareId = null; }

  function loadContacts(q) {
    fetch('/api/contacts?q=' + encodeURIComponent(q))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        shareContacts.innerHTML = '';
        if (!d.ok || !d.contacts.length) { shareContacts.innerHTML = '<div class="share-none">No contacts found.</div>'; return; }
        d.contacts.forEach(function (c) {
          var row = document.createElement('button'); row.className = 'share-contact';
          var av = document.createElement('span');
          av.className = 'avatar av-c' + (c.id % 5);
          av.style.cssText = 'width:34px;height:34px;font-size:13px;';
          if (c.has_avatar) { var im = document.createElement('img'); im.src = '/media/avatar/' + c.id; av.appendChild(im); }
          else av.textContent = c.initials;
          row.appendChild(av);
          var nm = document.createElement('span'); nm.textContent = c.name; row.appendChild(nm);
          var send = document.createElement('span'); send.className = 'sc-send'; send.textContent = 'Send'; row.appendChild(send);
          row.addEventListener('click', function () { shareTo(c.id, row); });
          shareContacts.appendChild(row);
        });
      });
  }
  function shareTo(recipientId, row) {
    if (!currentShareId) return;
    row.classList.add('sent');
    fetch('/api/share/post/' + currentShareId, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recipient_id: recipientId })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d.ok) { row.querySelector('.sc-send').textContent = 'Sent ✓'; toast('Shared in a message'); setTimeout(closeShare, 700); }
      else { row.classList.remove('sent'); toast(d.error || 'Could not share.', false); }
    }).catch(function () { row.classList.remove('sent'); toast('Could not share — try again.', false); });
  }

  $('shareClose').addEventListener('click', closeShare);
  shareModal.addEventListener('click', function (e) { if (e.target === shareModal) closeShare(); });
  $('shareCopyBtn').addEventListener('click', function () {
    shareUrl.select();
    (navigator.clipboard ? navigator.clipboard.writeText(shareUrl.value) : Promise.reject())
      .then(function () { $('shareCopyBtn').textContent = 'Copied ✓'; toast('Link copied to clipboard'); setTimeout(function () { $('shareCopyBtn').textContent = 'Copy link'; }, 1500); })
      .catch(function () { document.execCommand('copy'); toast('Link copied to clipboard'); });
  });
  var scT;
  if (shareContactSearch) shareContactSearch.addEventListener('input', function () {
    clearTimeout(scT); scT = setTimeout(function () { loadContacts(shareContactSearch.value.trim()); }, 200);
  });

  // ---------- search / filter feed ----------
  var roomSearch = $('roomSearch');
  if (roomSearch) {
    roomSearch.addEventListener('input', function () {
      var q = roomSearch.value.trim().toLowerCase();
      threadList.querySelectorAll(':scope > .post-card').forEach(function (card) {
        card.style.display = (!q || card.textContent.toLowerCase().indexOf(q) !== -1) ? '' : 'none';
      });
    });
  }

  // ---------- events ----------
  threadList.addEventListener('click', function (e) {
    var share = e.target.closest('.post-share');
    if (share) { openShare(share.getAttribute('data-post-id')); return; }
    if (e.target.classList.contains('post-reply-btn')) setReplyTarget(e.target.getAttribute('data-post-id'));
    else if (e.target.classList.contains('post-report')) reportPost(e.target.getAttribute('data-post-id'));
  });
  $('postSendBtn').addEventListener('click', submitPost);
  postInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitPost(); }
  });

  // ---------- permalink highlight ----------
  (function () {
    var m = location.search.match(/[?&]post=(\d+)/);
    if (!m) return;
    var el = document.getElementById('post-' + m[1]);
    if (el) { el.scrollIntoView({ block: 'center' }); el.classList.add('post-highlight'); }
  })();

  // ---------- polling + init ----------
  function poll() {
    if (document.visibilityState === 'hidden') return;
    fetch('/api/community/' + room + '/posts?since=' + lastId)
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d.ok) d.posts.forEach(addPostToDom); })
      .catch(function () {});
  }
  refreshTimes();
  setInterval(refreshTimes, 60000);
  setInterval(poll, 10000);
})();
