(function () {
    'use strict';

    // === Config ===
    const STORAGE_KEY = 'mikalia_session_id';

    // === State ===
    let sessionId = localStorage.getItem(STORAGE_KEY);
    let isStreaming = false;
    let shouldAutoScroll = true;

    // === DOM refs ===
    const messagesEl = document.getElementById('messages');
    const inputEl = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const form = inputEl.closest('form');
    const statusDot = document.querySelector('.header__status');

    // === Session ===
    function setSessionId(id) {
        sessionId = id;
        localStorage.setItem(STORAGE_KEY, id);
    }

    // === Message Rendering ===
    function addMessage(role, content) {
        var msgEl = createMessageElement(role);
        msgEl.querySelector('.message__content').innerHTML = renderMarkdown(content);
        messagesEl.appendChild(msgEl);
        scrollToBottom();
        return msgEl;
    }

    function createMessageElement(role) {
        var wrapper = document.createElement('div');
        wrapper.className = 'message message--' + role;
        var content = document.createElement('div');
        content.className = 'message__content';
        wrapper.appendChild(content);
        return wrapper;
    }

    function addTypingIndicator() {
        var el = document.createElement('div');
        el.className = 'message message--assistant';
        el.id = 'typing-indicator';
        el.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
        messagesEl.appendChild(el);
        scrollToBottom();
        return el;
    }

    function removeTypingIndicator() {
        var el = document.getElementById('typing-indicator');
        if (el) el.remove();
    }

    // === Markdown Renderer ===
    function renderMarkdown(text) {
        if (!text) return '';

        // Escape HTML first
        var html = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // Fenced code blocks: ```lang\n...\n```
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, function (_, lang, code) {
            return '<pre><code class="language-' + (lang || 'text') + '">' + code.trim() + '</code></pre>';
        });

        // Inline code: `...`
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Images: ![alt](data/images/path) — rewrite to served path
        html = html.replace(/!\[([^\]]*)\]\(data\/images\/([^)]+)\)/g, '<img src="/images/$2" alt="$1" loading="lazy">');
        // Images: ![alt](url)
        html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" loading="lazy">');

        // Links: [text](url)
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

        // Headers (h4 before h3 before h2 before h1 to avoid conflicts)
        html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

        // Bold: **text**
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Italic: *text*
        html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

        // Unordered lists: lines starting with - or *
        html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

        // Ordered lists: lines starting with 1. 2. etc
        html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

        // Paragraphs: double newlines
        html = html.replace(/\n\n+/g, '</p><p>');

        // Single newlines become <br> (but not inside pre blocks)
        html = html.replace(/\n/g, '<br>');

        // Wrap in paragraph if not starting with a block element
        if (!/^<(h[1-4]|pre|ul|ol|li|p)/.test(html)) {
            html = '<p>' + html + '</p>';
        }

        // Clean up empty paragraphs
        html = html.replace(/<p>\s*<\/p>/g, '');

        return html;
    }

    // === SSE Streaming Client ===
    async function sendMessage(text) {
        if (isStreaming || !text.trim()) return;

        isStreaming = true;
        sendBtn.disabled = true;

        // Show user message
        addMessage('user', text);

        // Show typing indicator
        addTypingIndicator();

        // Streaming state
        var assistantEl = null;
        var accumulated = '';

        try {
            var response = await fetch('/api/chat/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    session_id: sessionId
                })
            });

            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }

            removeTypingIndicator();

            var reader = response.body.getReader();
            var decoder = new TextDecoder();
            var buffer = '';

            while (true) {
                var result = await reader.read();
                if (result.done) break;

                buffer += decoder.decode(result.value, { stream: true });

                // Parse SSE lines
                var lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];
                    if (!line.startsWith('data: ')) continue;

                    try {
                        var event = JSON.parse(line.slice(6));

                        if (event.type === 'session') {
                            setSessionId(event.session_id);
                        } else if (event.type === 'chunk') {
                            accumulated += event.text;
                            if (!assistantEl) {
                                assistantEl = createMessageElement('assistant');
                                messagesEl.appendChild(assistantEl);
                            }
                            assistantEl.querySelector('.message__content').innerHTML = renderMarkdown(accumulated);
                            scrollToBottom();
                        } else if (event.type === 'done') {
                            // Streaming complete — nothing extra to do
                        } else if (event.type === 'error') {
                            showError(event.message || 'Error desconocido');
                        }
                    } catch (parseErr) {
                        // Skip malformed JSON lines silently
                    }
                }
            }

            // If no chunks were ever received, show a fallback
            if (!assistantEl && !accumulated) {
                showError('No se recibió respuesta.');
            }

            setStatus('connected');

        } catch (err) {
            removeTypingIndicator();
            showError('Error de conexión: ' + err.message);
            setStatus('disconnected');
        } finally {
            isStreaming = false;
            sendBtn.disabled = false;
            inputEl.focus();
        }
    }

    // === Error Display ===
    function showError(message) {
        var el = createMessageElement('assistant');
        el.querySelector('.message__content').innerHTML =
            '<p style="color: var(--error);">\u26A0 ' + escapeHtml(message) + '</p>';
        messagesEl.appendChild(el);
        scrollToBottom();
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // === Status Indicator ===
    function setStatus(status) {
        if (!statusDot) return;
        statusDot.style.background = status === 'connected' ? '#4caf50' : '#e74c3c';
    }

    // === Auto-scroll ===
    function scrollToBottom() {
        if (!shouldAutoScroll) return;
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function setupAutoScroll() {
        messagesEl.addEventListener('scroll', function () {
            var threshold = 100;
            var atBottom = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < threshold;
            shouldAutoScroll = atBottom;
        });
    }

    // === Auto-grow Textarea ===
    function setupTextarea() {
        inputEl.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 150) + 'px';
        });
    }

    // === Event Handlers ===
    function handleSubmit(e) {
        e.preventDefault();
        var text = inputEl.value.trim();
        if (!text) return;
        inputEl.value = '';
        inputEl.style.height = 'auto';
        sendMessage(text);
    }

    function handleKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
        }
    }

    // === Init ===
    function init() {
        form.addEventListener('submit', handleSubmit);
        inputEl.addEventListener('keydown', handleKeydown);
        setupAutoScroll();
        setupTextarea();
        setStatus('connected');
        inputEl.focus();
    }

    init();
})();
