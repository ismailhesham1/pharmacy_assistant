import { useEffect, useRef, useState } from "react";
import "./App.css";

const WEBSOCKET_URL = "ws://localhost:8000/ws/chat";

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

function App() {
  const [messages, setMessages] = useState([]); // {role: "user" | "assistant", content, status}
  const [input, setInput] = useState("");
  const [connectionState, setConnectionState] = useState("connecting"); // connecting | open | closed
  const wsRef = useRef(null);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  // Open the WebSocket connection once, when the component first mounts.
  // Close it when the component unmounts (cleanup function) - this is the
  // standard React pattern for anything with a lifecycle outside React itself.
  useEffect(() => {
    const ws = new WebSocket(WEBSOCKET_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnectionState("open");
    ws.onclose = () => setConnectionState("closed");
    ws.onerror = () => setConnectionState("closed");
    // recieves msgs
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

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

    return () => ws.close();
  }, []); // empty dependency array = run once on mount, not on every re-render

  // Keep the latest message in view as tokens stream in.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

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

        <div className={`status status--${connectionState}`}>
          <CrossIcon className="status__dot" />
          <span>{STATUS_LABEL[connectionState]}</span>
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
                    <p className="message__text" dir="auto">
                      {m.content}
                    </p>
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
