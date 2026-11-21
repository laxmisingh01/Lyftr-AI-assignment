import { useEffect, useRef, useState } from "react";
import { errorMessage, sendChat } from "./api.js";
import MarkdownContent from "./MarkdownContent.jsx";

function createSessionId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function AssistantMark() {
  return (
    <span className="assistant-mark" aria-hidden="true">
      L
    </span>
  );
}

function Metadata({ metadata }) {
  return (
    <dl className="metadata" aria-label="Response metadata">
      <div>
        <dt>Source</dt>
        <dd data-testid="meta-source">{metadata.resolution_source}</dd>
      </div>
      <div>
        <dt>Model</dt>
        <dd data-testid="meta-model">{metadata.model}</dd>
      </div>
      <div>
        <dt>Latency</dt>
        <dd data-testid="meta-latency">{metadata.latency_ms} ms</dd>
      </div>
      <div>
        <dt>Input tokens</dt>
        <dd data-testid="meta-input-tokens">{metadata.input_tokens}</dd>
      </div>
      <div>
        <dt>Output tokens</dt>
        <dd data-testid="meta-output-tokens">{metadata.output_tokens}</dd>
      </div>
    </dl>
  );
}

function AssistantMessage({ message }) {
  return (
    <article className="message-row assistant-row" data-testid="assistant-message">
      <AssistantMark />
      <div className="message-column">
        <div className="message-author">Lyftr AI</div>
        <div className="message-bubble assistant-bubble">
          <MarkdownContent content={message.content} />
        </div>
        {message.metadata && <Metadata metadata={message.metadata} />}
      </div>
    </article>
  );
}

function UserMessage({ message }) {
  return (
    <article className="message-row user-row">
      <div className="message-column">
        <div className="message-author">You</div>
        <div className="message-bubble user-bubble">{message.content}</div>
      </div>
    </article>
  );
}

export default function App() {
  const [sessionId] = useState(createSessionId);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [systemPromptChanged, setSystemPromptChanged] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const conversationEndRef = useRef(null);

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading, error]);

  async function submitMessage(event) {
    event?.preventDefault();
    const message = draft.trim();
    if (!message || loading) return;

    setLoading(true);
    setError("");

    const payload = { session_id: sessionId, message };
    if (systemPromptChanged) {
      payload.system_prompt = systemPrompt.trim();
    }

    try {
      const response = await sendChat(payload);
      setMessages((current) => [
        ...current,
        { id: createSessionId(), role: "user", content: message },
        {
          id: createSessionId(),
          role: "assistant",
          content: response.reply,
          metadata: response.metadata,
        },
      ]);
      setDraft("");
      setSystemPromptChanged(false);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }

  function handleMessageKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitMessage(event);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#home" aria-label="Lyftr AI home">
          <span className="brand-mark" aria-hidden="true">L</span>
          <span>Lyftr <strong>AI</strong></span>
        </a>
        <div className="workspace-label">
          <span className="status-dot" aria-hidden="true" />
          New conversation
        </div>
        <div className="session-badge" title={`Session ${sessionId}`}>
          <span className="session-dot" aria-hidden="true" />
          Private session
        </div>
      </header>

      <section className="chat-panel" aria-label="Lyftr AI conversation">
        <div className="conversation-heading">
          <div className="heading-mark"><AssistantMark /></div>
          <div>
            <h1>How can I help?</h1>
            <p>Ask a question or start working through an idea.</p>
          </div>
        </div>

        <div className="conversation" aria-live="polite" aria-relevant="additions">
          {messages.length === 0 && !loading && (
            <div className="empty-state">
              <div className="empty-icon" aria-hidden="true">✳</div>
              <h2>Your next idea starts here.</h2>
              <p>Send a message to begin a conversation with Lyftr AI.</p>
            </div>
          )}

          {messages.map((message) =>
            message.role === "assistant" ? (
              <AssistantMessage key={message.id} message={message} />
            ) : (
              <UserMessage key={message.id} message={message} />
            ),
          )}

          {loading && (
            <div className="message-row assistant-row loading-row" role="status" aria-label="Assistant is generating a response">
              <AssistantMark />
              <div className="message-column">
                <div className="message-author">Lyftr AI</div>
                <div className="message-bubble assistant-bubble loading-bubble" data-testid="loading-indicator">
                  <span /> <span /> <span />
                  <span className="loading-label">Thinking</span>
                </div>
              </div>
            </div>
          )}

          {error && <div className="error-banner" role="alert" data-testid="chat-error">{error}</div>}
          <div ref={conversationEndRef} />
        </div>

        <form className="composer" onSubmit={submitMessage}>
          <label className="system-prompt-label" htmlFor="system-prompt-input">
            System prompt <span>Optional · applied to this session</span>
          </label>
          <textarea
            id="system-prompt-input"
            data-testid="system-prompt-input"
            className="system-prompt-input"
            value={systemPrompt}
            onChange={(event) => {
              setSystemPrompt(event.target.value);
              setSystemPromptChanged(true);
            }}
            placeholder="Set a tone or give the assistant extra context"
            rows={2}
            disabled={loading}
          />
          <div className="composer-row">
            <textarea
              data-testid="chat-input"
              className="chat-input"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleMessageKeyDown}
              placeholder="Message Lyftr AI…"
              aria-label="Message Lyftr AI"
              rows={1}
              disabled={loading}
            />
            <button
              data-testid="send-button"
              className="send-button"
              type="submit"
              disabled={loading || !draft.trim()}
              aria-label={loading ? "Sending message" : "Send message"}
            >
              {loading ? (
                <span className="button-spinner" aria-hidden="true" />
              ) : (
                <svg aria-hidden="true" viewBox="0 0 20 20" fill="none">
                  <path d="M3.25 10h13.5M10.5 3.75 16.75 10l-6.25 6.25" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
              <span>{loading ? "Sending" : "Send"}</span>
            </button>
          </div>
          <div className="composer-hint">Enter to send <span>·</span> Shift + Enter for a new line</div>
        </form>
      </section>

      <footer className="page-footer">Lyftr AI can make mistakes. Check important information.</footer>
    </main>
  );
}
