// Minimal, safe markdown-ish renderer for chat/community message content
// (both Amara's replies and human posts go through the same renderer, for
// consistent formatting). Not a full CommonMark implementation -- just what
// actually shows up in practice: **bold**, *italic*/_italic_, `code`,
// bullet/numbered lists, and paragraphs.
//
// Safety: escapeHtml() runs first and unconditionally, before any markdown
// pattern is applied, so raw HTML in a message (human-typed or model output)
// can never reach innerHTML as markup -- only the limited tags this file
// itself adds.
(function (global) {
  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function inline(s) {
    s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/__([^_\n]+)__/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
    s = s.replace(/(^|[^_])_([^_\n]+)_(?!_)/g, '$1<em>$2</em>');
    s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    return s;
  }

  function renderChatMarkdown(raw) {
    var lines = escapeHtml(raw).split('\n');
    var html = '';
    var listBuffer = [];
    var listType = null; // 'ul' | 'ol'
    var paraBuffer = [];

    function flushList() {
      if (!listBuffer.length) return;
      var tag = listType === 'ol' ? 'ol' : 'ul';
      html += '<' + tag + '>' + listBuffer.map(function (li) {
        return '<li>' + inline(li) + '</li>';
      }).join('') + '</' + tag + '>';
      listBuffer = [];
      listType = null;
    }

    function flushPara() {
      if (!paraBuffer.length) return;
      html += '<p>' + paraBuffer.map(inline).join('<br>') + '</p>';
      paraBuffer = [];
    }

    lines.forEach(function (line) {
      var trimmed = line.trim();
      var bulletMatch = /^[*-]\s+(.*)$/.exec(trimmed);
      var numberMatch = /^\d+\.\s+(.*)$/.exec(trimmed);
      if (bulletMatch) {
        flushPara();
        if (listType && listType !== 'ul') flushList();
        listType = 'ul';
        listBuffer.push(bulletMatch[1]);
      } else if (numberMatch) {
        flushPara();
        if (listType && listType !== 'ol') flushList();
        listType = 'ol';
        listBuffer.push(numberMatch[1]);
      } else if (trimmed === '') {
        flushList();
        flushPara();
      } else {
        flushList();
        paraBuffer.push(trimmed);
      }
    });
    flushList();
    flushPara();
    return html;
  }

  global.renderChatMarkdown = renderChatMarkdown;
})(window);
