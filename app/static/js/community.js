(function () {
  var $ = function (id) { return document.getElementById(id); };
  var threadList = $('threadList');
  var room = threadList.getAttribute('data-room');
  var lastId = parseInt(threadList.getAttribute('data-last-id'), 10) || 0;
  var postInput = $('postInput');
  var replyToId = $('replyToId');
  var replyContext = $('replyContext');

  // Turn an ISO-UTC timestamp (stored without a trailing 'Z') into a
  // friendly relative label like "just now" / "4m ago" / "2h ago".
  function relativeTime(iso) {
    if (!iso) return '';
    var t = Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z');
    if (isNaN(t)) return iso;
    var s = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (s < 45) return 'just now';
    var m = Math.round(s / 60);
    if (m < 60) return m + 'm ago';
    var h = Math.round(m / 60);
    if (h < 24) return h + 'h ago';
    var d = Math.round(h / 24);
    if (d < 7) return d + 'd ago';
    return new Date(t).toLocaleDateString();
  }

  // Format the timestamps already rendered by the server on first paint.
  function formatExistingTimes() {
    var els = threadList.querySelectorAll('.post-time');
    for (var i = 0; i < els.length; i++) {
      var raw = els[i].getAttribute('data-iso') || els[i].textContent.trim();
      els[i].setAttribute('data-iso', raw);
      els[i].textContent = relativeTime(raw);
    }
  }

  function buildPostCard(post, isReply) {
    var card = document.createElement('div');
    card.className = 'post-card' + (isReply ? ' post-reply' : '');
    card.setAttribute('data-post-id', post.id);

    var head = document.createElement('div');
    head.className = 'post-head';

    var author = document.createElement('span');
    author.className = 'post-author' + (post.is_ai ? ' post-author-ai' : '');
    author.textContent = post.author_label;
    head.appendChild(author);

    var time = document.createElement('span');
    time.className = 'post-time';
    time.setAttribute('data-iso', post.created_at);
    time.textContent = relativeTime(post.created_at);
    head.appendChild(time);

    if (!post.is_ai) {
      var reportBtn = document.createElement('button');
      reportBtn.className = 'post-report';
      reportBtn.setAttribute('data-post-id', post.id);
      reportBtn.textContent = 'Report';
      head.appendChild(reportBtn);
    }

    card.appendChild(head);

    var content = document.createElement('div');
    content.className = 'post-content';
    content.textContent = post.content;
    card.appendChild(content);

    if (!isReply) {
      var repliesDiv = document.createElement('div');
      repliesDiv.className = 'post-replies';
      card.appendChild(repliesDiv);

      var replyBtn = document.createElement('button');
      replyBtn.className = 'post-reply-btn';
      replyBtn.setAttribute('data-post-id', post.id);
      replyBtn.textContent = 'Reply';
      card.appendChild(replyBtn);
    }

    return card;
  }

  function addPostToDom(post) {
    if (post.id > lastId) lastId = post.id;
    threadList.setAttribute('data-last-id', String(lastId));

    if (!post.parent_id) {
      threadList.appendChild(buildPostCard(post, false));
      return;
    }
    var parentCard = threadList.querySelector('[data-post-id="' + post.parent_id + '"]');
    if (parentCard) {
      var repliesDiv = parentCard.querySelector('.post-replies');
      if (repliesDiv) {
        repliesDiv.appendChild(buildPostCard(post, true));
        return;
      }
    }
    // Parent not found in the currently loaded page (older post) -- show as
    // a standalone top-level card rather than silently dropping it.
    threadList.appendChild(buildPostCard(post, false));
  }

  function setReplyTarget(postId) {
    replyToId.value = postId || '';
    if (postId) {
      replyContext.style.display = 'block';
      replyContext.textContent = 'Replying to post #' + postId + ' — ';
      var clearBtn = document.createElement('button');
      clearBtn.textContent = 'cancel';
      clearBtn.style.cssText = 'background:none;border:none;color:var(--accent);text-decoration:underline;cursor:pointer;';
      clearBtn.addEventListener('click', function () { setReplyTarget(null); });
      replyContext.appendChild(clearBtn);
      postInput.focus();
    } else {
      replyContext.style.display = 'none';
      replyContext.textContent = '';
    }
  }

  function submitPost() {
    var content = postInput.value.trim();
    if (!content) return;
    var btn = $('postSendBtn');
    btn.disabled = true;

    fetch('/api/community/' + room + '/posts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: content, parent_id: replyToId.value || null })
    }).then(function (res) {
      return res.json().then(function (data) { return { ok: res.ok, data: data }; });
    }).then(function (result) {
      btn.disabled = false;
      if (!result.ok) {
        alert((result.data && result.data.error) || 'Could not post — try again.');
        return;
      }
      postInput.value = '';
      setReplyTarget(null);
      addPostToDom(result.data.post);
      if (result.data.ai_reply) addPostToDom(result.data.ai_reply);
    }).catch(function () {
      btn.disabled = false;
      alert('Could not reach the server — check your connection and try again.');
    });
  }

  function reportPost(postId) {
    var reason = window.prompt('Why are you reporting this post? (optional)') || '';
    fetch('/api/community/posts/' + postId + '/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason })
    }).then(function (res) { return res.json(); }).then(function (data) {
      if (data.ok) alert('Thanks — a TGM staff member will review this.');
    });
  }

  threadList.addEventListener('click', function (e) {
    if (e.target.classList.contains('post-reply-btn')) {
      setReplyTarget(e.target.getAttribute('data-post-id'));
    } else if (e.target.classList.contains('post-report')) {
      reportPost(e.target.getAttribute('data-post-id'));
    }
  });

  $('postSendBtn').addEventListener('click', submitPost);
  postInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitPost();
    }
  });

  function poll() {
    if (document.visibilityState === 'hidden') return;
    fetch('/api/community/' + room + '/posts?since=' + lastId)
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.ok) data.posts.forEach(addPostToDom);
      })
      .catch(function () { /* silent -- next poll will retry */ });
  }

  formatExistingTimes();
  // Keep every visible "Xm ago" label honest as time passes.
  setInterval(function () {
    var els = threadList.querySelectorAll('.post-time[data-iso]');
    for (var i = 0; i < els.length; i++) {
      els[i].textContent = relativeTime(els[i].getAttribute('data-iso'));
    }
  }, 60000);

  setInterval(poll, 10000);
})();
