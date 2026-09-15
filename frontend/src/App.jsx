import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./App.css";

const WEBSOCKET_URL = "ws://localhost:8000/ws/chat";
const THREAD_ID_KEY = "pharmacy_thread_id";
const RECONNECT_DELAY_MS = 2000;

// Conversation id, persisted in localStorage so a page refresh (or a
// dropped connection reconnecting) resumes the same thread server-side
// instead of starting a blank one. Falls back to null if localStorage is
// unavailable (e.g. private browsing) - the chat still works, it just
// won't survive a refresh in that case.
function getStoredThreadId() {
  try {
    return localStorage.getItem(THREAD_ID_KEY);
  } catch {
    return null;
  }
}

function storeThreadId(id) {
  try {
    localStorage.setItem(THREAD_ID_KEY, id);
  } catch {
    // ignore - see getStoredThreadId
  }
}

function buildWebSocketUrl() {
  const threadId = getStoredThreadId();
  return threadId ? `${WEBSOCKET_URL}?thread_id=${encodeURIComponent(threadId)}` : WEBSOCKET_URL;
}

// Friendly labels for the tool names the backend reports mid-turn (see
// app/agent/tools.py) - shown next to a pulsing cross while the agent works.
const TOOL_LABELS = {
  search_products: "Searching products...",
  search_policy: "Checking policies...",
  get_product_details: "Looking up product details...",
};

const SUGGESTIONS = [
  "Do you have paracetamol in stock?",
  "What are your delivery options?",
  "Can I get a prescription refill?",
];

const STATUS_LABEL = {
  connecting: "Connecting",
  open: "Online",
  closed: "Offline",
};

// The pharmacy cross - the universal mark of a pharmacy, used both as the
// brand mark and, pulsing, as the "the assistant is working" indicator.
function CrossIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M10 3h4v7h7v4h-7v7h-4v-7H3v-4h7z" />
    </svg>
  );
}

function SendIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M22 2 11 13" />
      <path d="M22 2 15 22l-4-9-9-4 20-7Z" />
    </svg>
  );
}

// Compose/pencil glyph - the conventional "new chat" mark, kept visually
// distinct from the brand cross so the two aren't mistaken for each other.
function NewChatIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

// Renders the assistant's Markdown (bold text, numbered/bulleted lists,
// tables - the model frequently produces all of these for product
// comparisons) as real structured HTML instead of literal asterisks and
// dashes. remark-gfm adds GitHub-flavored table support specifically,
// since product comparison responses often come back as Markdown tables.
function MessageContent({ text }) {
  return (
    <div className="message__markdown" dir="auto">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

function App() {
  const [messages, setMessages] = useState([]); // {role: "user" | "assistant", content, status}
  const [input, setInput] = useState("");
  const [connectionState, setConnectionState] = useState("connecting"); // connecting | open | closed
  const wsRef = useRef(null);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  // Wires up a fresh WebSocket connection (using whatever thread_id is
  // currently in localStorage) and stores it in wsRef. Pulled into its own
  // function so the initial mount, the auto-reconnect retry, and the "New
  // Chat" button all go through the exact same connect/reconnect logic
  // instead of multiple copies drifting apart.
  function connect() {
    const ws = new WebSocket(buildWebSocketUrl());
    wsRef.current = ws;

    ws.onopen = () => setConnectionState("open");
    ws.onclose = () => {
      setConnectionState("closed");
      // Automatically retry after a short delay if the connection drops
      // unexpectedly (e.g. the backend restarts) - without this, the user
      // is stuck seeing "Offline" until they manually refresh the page.
      // startNewChat() below explicitly detaches this handler before
      // closing the old socket, so an intentional new-chat close never
      // triggers this retry.
      setTimeout(connect, RECONNECT_DELAY_MS);
    };
    ws.onerror = () => setConnectionState("closed");
    // recieves msgs
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      // Sent once, right after connecting: the server's thread_id (so we
      // can remember it even on a first-ever visit) plus any messages
      // already saved for this thread - restores the conversation after a
      // refresh or a reconnect instead of starting from an empty screen.
      if (data.type === "history") {
        if (data.thread_id) storeThreadId(data.thread_id);
        setMessages(data.messages.map((m) => ({ role: m.role, content: m.content, status: null })));
        return;
      }

      setMessages((prev) => {
        const lastMessage = prev[prev.length - 1];
        if (!lastMessage) return prev;

        // Build a NEW message object rather than mutating lastMessage in
        // place. React 18+ StrictMode intentionally invokes state updater
        // functions twice in development to catch exactly this kind of
        // impurity - mutating in place made the second invocation see
        // already-updated state and re-apply the change, doubling every
        // token on screen.
        let nextLastMessage;
        if (data.type === "token") {
          // Append this token onto the in-progress assistant message -
          // this incremental append is what creates the "streaming" effect.
          nextLastMessage = { ...lastMessage, content: lastMessage.content + data.content };
        } else if (data.type === "replace") {
          // Sent once at the end of a turn with the true final message
          // content - overwrites whatever was streamed in via "token"
          // events rather than appending, so the displayed message is
          // always correct even if it differs from what was streamed live
          // (e.g. the backend substituted a fallback message).
          nextLastMessage = { ...lastMessage, content: data.content };
        } else if (data.type === "tool_call") {
          nextLastMessage = { ...lastMessage, status: TOOL_LABELS[data.tool] || `Using ${data.tool}...` };
        } else if (data.type === "tool_result" || data.type === "done") {
          nextLastMessage = { ...lastMessage, status: null }; // clear the status once the tool call (or turn) finishes
        } else {
          return prev;
        }

        return [...prev.slice(0, -1), nextLastMessage];
      });
    };

    return ws;
  }

  // Open the WebSocket connection once, when the component first mounts.
  // Close it when the component unmounts (cleanup function) - this is the
  // standard React pattern for anything with a lifecycle outside React itself.
  useEffect(() => {
    const ws = connect();
    return () => ws.close();
  }, []); // empty dependency array = run once on mount, not on every re-render

  // Keep the latest message in view as tokens stream in.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  // Starts a brand-new conversation: swaps in a fresh thread_id, clears the
  // messages shown locally, and reconnects the socket using that new id.
  // The backend already treats an unseen thread_id as a blank conversation,
  // so nothing stored server-side under the old thread_id is touched here -
  // this only changes which thread the current session points to.
  function startNewChat() {
    const newThreadId = crypto.randomUUID();
    storeThreadId(newThreadId);
    setMessages([]);
    setConnectionState("connecting");

    // Detach the old socket's handlers before closing it - this both
    // avoids a race where the old socket's async close event could stomp
    // on the new connection's state, AND (importantly) prevents the
    // auto-reconnect logic in onclose from firing for this intentional,
    // expected close.
    const oldWs = wsRef.current;
    if (oldWs) {
      oldWs.onopen = null;
      oldWs.onclose = null;
      oldWs.onerror = null;
      oldWs.onmessage = null;
      oldWs.close();
    }

    connect();
  }

  function sendMessage(text) {
    const content = (text ?? input).trim();
    if (!content || connectionState !== "open") return;

    // Add the user's message, plus an empty placeholder for the assistant's
    // reply that will be filled in token-by-token as "token" events arrive.
    setMessages((prev) => [
      ...prev,
      { role: "user", content },
      { role: "assistant", content: "", status: null },
    ]);
 // sends msgs
    wsRef.current.send(JSON.stringify({ content }));
    setInput("");
    requestAnimationFrame(() => {
      if (inputRef.current) inputRef.current.style.height = "auto";
    });
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function handleInput(e) {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }

  return (
    <div className="app">
      <header className="app__header">
        <div className="brand">
          <span className="brand__mark">
            <CrossIcon />
          </span>
          <div>
            <p className="brand__eyebrow">Pharmacy</p>
            <h1 className="brand__title">Assistant</h1>
          </div>
        </div>

        <div className="header__actions">
          <button
            type="button"
            className="btn-newchat"
            onClick={startNewChat}
            aria-label="Start a new chat"
          >
            <NewChatIcon />
            <span>New chat</span>
          </button>

          <div className={`status status--${connectionState}`} role="status" aria-live="polite">
            <CrossIcon className="status__dot" />
            <span>{STATUS_LABEL[connectionState]}</span>
          </div>
        </div>
      </header>

      <main className="chat">
        {messages.length === 0 ? (
          <div className="empty">
            <CrossIcon className="empty__icon" />
            <p className="empty__title">
              Ask me about products, dosages, or store policies - I'll search the
              catalog and policy docs to help.
            </p>
            <div className="empty__suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chip" onClick={() => sendMessage(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="messages">
            {messages.map((m, i) => (
              <div className={`message message--${m.role}`} key={i}>
                {m.role === "assistant" && (
                  <span className="message__avatar">
                    <CrossIcon />
                  </span>
                )}
                <div className="message__bubble">
                  {m.status && (
                    <span className="typing">
                      <CrossIcon className="typing__dot" />
                      {m.status}
                    </span>
                  )}
                  {m.content && (
                    m.role === "assistant"
                      ? <MessageContent text={m.content} />
                      : <p className="message__text" dir="auto">{m.content}</p>
                  )}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </main>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          sendMessage();
        }}
      >
        <textarea
          ref={inputRef}
          className="composer__input"
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask about a product, dosage, or policy..."
          aria-label="Message"
          rows={1}
        />
        <button
          type="submit"
          className="composer__send"
          disabled={!input.trim() || connectionState !== "open"}
        >
          <SendIcon />
          <span>Send</span>
        </button>
      </form>
    </div>
  );
}

export default App;