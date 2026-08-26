import { useEffect, useMemo, useRef, useState } from "react";
import {
    Bot,
    Database,
    Menu,
    Plus,
    Send,
    ShieldCheck,
    Sparkles,
    Square,
    User,
    Wifi,
    WifiOff,
    X,
} from "lucide-react";
import "./interrupt.css";

let idCounter = 0;
const generateId = () => `${Date.now()}-${++idCounter}-${Math.random().toString(36).slice(2, 9)}`;
const createConversation = () => ({ id: generateId(), title: "New database chat", messages: [] });
const socketUrl = (mode) => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/${mode}`;
const displayText = (value) => {
    if (value == null) return "";
    if (typeof value === "string") return value;
    try { return JSON.stringify(value, null, 2); } catch { return String(value); }
};

function ChatMessage({ message }) {
    const user = message.role === "user";
    return (
        <div className={`message-row ${user ? "message-row-user" : "message-row-assistant"}`}>
            {!user && <div className="avatar avatar-assistant"><Bot size={18} /></div>}
            <div className={`message-bubble ${user ? "message-bubble-user" : "message-bubble-assistant"}`}>
                <div className="message-content">{message.content}</div>
                {message.streaming && <span className="streaming-cursor" />}
            </div>
            {user && <div className="avatar avatar-user"><User size={18} /></div>}
        </div>
    );
}

function InterruptDialog({ request, input, setInput, submit }) {
    const [selectedDecision, setSelectedDecision] = useState("");
    const [editedActions, setEditedActions] = useState({});

    useEffect(() => {
        setSelectedDecision("");
        setEditedActions({});
        setInput("");
    }, [request, setInput]);

    if (!request) return null;

    const value = request.value;

    // Existing simple HITL input popup.
    if (!value || typeof value === "string" || value.type !== "tool_review") {
        const title = value?.title || "Additional information required";
        const message =
            typeof value === "string"
                ? value
                : value?.message || "The agent requires your input.";
        const placeholder = value?.placeholder || "Enter the requested details";

        const submitSimpleInput = () => {
            const enteredValue = input.trim();
            if (enteredValue) submit(enteredValue);
        };

        return (
            <div className="interrupt-overlay" role="dialog" aria-modal="true">
                <div className="interrupt-modal">
                    <div className="interrupt-header">
                        <div className="interrupt-icon">
                            <ShieldCheck size={25} />
                        </div>
                        <div>
                            <h2>{title}</h2>
                            <p>{message}</p>
                        </div>
                    </div>

                    <textarea
                        className="interrupt-textarea"
                        rows={4}
                        autoFocus
                        value={input}
                        placeholder={placeholder}
                        onChange={(event) => setInput(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === "Enter" && !event.shiftKey) {
                                event.preventDefault();
                                submitSimpleInput();
                            }
                        }}
                    />

                    <div className="interrupt-actions">
                        <button
                            type="button"
                            className="interrupt-button interrupt-button-primary"
                            disabled={!input.trim()}
                            onClick={submitSimpleInput}
                        >
                            Continue
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    // Structured tool-review HITL popup.
    const actions = Array.isArray(value.actions) ? value.actions : [];

    function selectDecision(decision) {
        setSelectedDecision(decision);
        setInput("");

        if (decision === "edit") {
            const emptyEditValues = {};

            actions.forEach((action, actionIndex) => {
                const actionKey = `${action.name}-${actionIndex}`;
                emptyEditValues[actionKey] = {};

                Object.keys(action.args || {}).forEach((argumentName) => {
                    // Empty means keep the original value.
                    emptyEditValues[actionKey][argumentName] = "";
                });
            });

            setEditedActions(emptyEditValues);
        }
    }

    function updateEditedArgument(actionKey, argumentName, newValue) {
        setEditedActions((current) => ({
            ...current,
            [actionKey]: {
                ...(current[actionKey] || {}),
                [argumentName]: newValue,
            },
        }));
    }

    function submitReview() {
        if (!selectedDecision) return;

        if (selectedDecision === "approve") {
            submit({ decision: "approve" });
            return;
        }

        if (selectedDecision === "respond" || selectedDecision === "reject") {
            const message = input.trim();
            if (!message) return;
            submit({ decision: selectedDecision, message });
            return;
        }

        if (selectedDecision === "edit") {
            const editedActionList = actions.map((action, actionIndex) => {
                const actionKey = `${action.name}-${actionIndex}`;
                const enteredValues = editedActions[actionKey] || {};
                const changedArguments = {};

                Object.entries(enteredValues).forEach(([argumentName, newValue]) => {
                    const normalizedValue =
                        typeof newValue === "string" ? newValue.trim() : newValue;

                    if (
                        normalizedValue !== "" &&
                        normalizedValue !== null &&
                        normalizedValue !== undefined
                    ) {
                        changedArguments[argumentName] = normalizedValue;
                    }
                });

                return {
                    action_index: actionIndex,
                    action_name: action.name,
                    args: changedArguments,
                };
            });

            submit({
                decision: "edit",
                edited_actions: editedActionList,
            });
        }
    }

    const requiresMessage =
        selectedDecision === "respond" || selectedDecision === "reject";
    const submitDisabled =
        !selectedDecision || (requiresMessage && !input.trim());

    return (
        <div
            className="interrupt-overlay"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tool-review-title"
        >
            <div className="interrupt-modal tool-review-modal">
                <div className="interrupt-header">
                    <div className="interrupt-icon">
                        <ShieldCheck size={25} />
                    </div>
                    <div>
                        <h2 id="tool-review-title">
                            {value.title || "Review tool execution"}
                        </h2>
                        <p>{value.message || "Review the requested tool actions."}</p>
                    </div>
                </div>

                {value.table && (
                    <div className="tool-review-table">
                        Target table: <strong>{value.table}</strong>
                    </div>
                )}

                <div className="tool-review-actions-list">
                    {actions.map((action, actionIndex) => {
                        const actionKey = `${action.name}-${actionIndex}`;

                        return (
                            <div className="tool-review-action-card" key={actionKey}>
                                <div className="tool-review-action-header">
                                    <div>
                                        <span className="tool-review-number">
                                            Action {actionIndex + 1}
                                        </span>
                                        <h3>{action.name}</h3>
                                    </div>
                                    <span className="tool-risk-label">Risk review</span>
                                </div>

                                <p className="tool-risk-message">
                                    {action.risk_analysis ||
                                        action.risk ||
                                        "Risk analysis unavailable."}
                                </p>

                                <div className="original-arguments">
                                    <h4>Current tool arguments</h4>
                                    <pre className="interrupt-details">
                                        {displayText(action.args || {})}
                                    </pre>
                                </div>

                                {selectedDecision === "edit" && (
                                    <div className="edit-arguments">
                                        {Object.entries(action.args || {}).map(
                                            ([argumentName, originalValue]) => (
                                                <label className="edit-field" key={argumentName}>
                                                    <span>{argumentName}</span>
                                                    <input
                                                        type="text"
                                                        value={
                                                            editedActions[actionKey]?.[argumentName] ?? ""
                                                        }
                                                        placeholder="Leave empty to keep current value"
                                                        onChange={(event) =>
                                                            updateEditedArgument(
                                                                actionKey,
                                                                argumentName,
                                                                event.target.value
                                                            )
                                                        }
                                                    />
                                                    <small>
                                                        Current value: {displayText(originalValue)}
                                                    </small>
                                                </label>
                                            )
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>

                <div className="decision-selector">
                    <button
                        type="button"
                        className={`decision-button decision-approve ${selectedDecision === "approve" ? "decision-button-selected" : ""
                            }`}
                        onClick={() => selectDecision("approve")}
                    >
                        Approve
                    </button>
                    <button
                        type="button"
                        className={`decision-button decision-edit ${selectedDecision === "edit" ? "decision-button-selected" : ""
                            }`}
                        onClick={() => selectDecision("edit")}
                    >
                        Edit
                    </button>
                    <button
                        type="button"
                        className={`decision-button decision-respond ${selectedDecision === "respond" ? "decision-button-selected" : ""
                            }`}
                        onClick={() => selectDecision("respond")}
                    >
                        Respond
                    </button>
                    <button
                        type="button"
                        className={`decision-button decision-reject ${selectedDecision === "reject" ? "decision-button-selected" : ""
                            }`}
                        onClick={() => selectDecision("reject")}
                    >
                        Reject
                    </button>
                </div>

                {selectedDecision === "approve" && (
                    <div className="decision-help approve-help">
                        The displayed tool actions will run using their current arguments.
                    </div>
                )}

                {selectedDecision === "edit" && (
                    <div className="decision-help edit-help">
                        Leave a field empty to keep its current value. Enter a value only
                        for arguments you want to change.
                    </div>
                )}

                {selectedDecision === "respond" && (
                    <textarea
                        className="interrupt-textarea"
                        rows={4}
                        autoFocus
                        value={input}
                        placeholder="Enter your response to the agent"
                        onChange={(event) => setInput(event.target.value)}
                    />
                )}

                {selectedDecision === "reject" && (
                    <textarea
                        className="interrupt-textarea"
                        rows={4}
                        autoFocus
                        value={input}
                        placeholder="Enter the reason for rejection"
                        onChange={(event) => setInput(event.target.value)}
                    />
                )}

                <div className="interrupt-actions">
                    <button
                        type="button"
                        className="interrupt-button interrupt-button-primary"
                        disabled={submitDisabled}
                        onClick={submitReview}
                    >
                        {selectedDecision === "approve"
                            ? "Approve and continue"
                            : selectedDecision === "edit"
                                ? "Apply changes and continue"
                                : selectedDecision === "respond"
                                    ? "Send response"
                                    : selectedDecision === "reject"
                                        ? "Reject actions"
                                        : "Select a decision"}
                    </button>
                </div>
            </div>
        </div>
    );
}
export default function App() {
    const initial = useRef(createConversation());
    const [conversations, setConversations] = useState([initial.current]);
    const [activeId, setActiveId] = useState(initial.current.id);
    const [mode, setMode] = useState("chat");
    const [input, setInput] = useState("");
    const [status, setStatus] = useState("connecting");
    const [streaming, setStreaming] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [notice, setNotice] = useState("");
    const [interrupt, setInterrupt] = useState(null);
    const [interruptInput, setInterruptInput] = useState("");
    const socketRef = useRef(null);
    const activeIdRef = useRef(initial.current.id);
    const bottomRef = useRef(null);

    useEffect(() => { activeIdRef.current = activeId; }, [activeId]);
    const active = useMemo(() => conversations.find((c) => c.id === activeId) || conversations[0], [conversations, activeId]);
    const updateConversation = (id, updater) => setConversations((items) => items.map((item) => item.id === id ? updater(item) : item));

    const finishAssistant = () => updateConversation(activeIdRef.current, (conversation) => ({
        ...conversation,
        messages: conversation.messages.map((message, index, all) =>
            index === all.length - 1 && message.role === "assistant" ? { ...message, streaming: false } : message
        ),
    }));

    const appendChunk = (content) => {
        if (!content) return;
        updateConversation(activeIdRef.current, (conversation) => {
            const messages = [...conversation.messages];
            const last = messages.at(-1);
            if (last?.role === "assistant" && last.streaming) messages[messages.length - 1] = { ...last, content: last.content + content };
            else messages.push({ id: generateId(), role: "assistant", content, streaming: true });
            return { ...conversation, messages };
        });
    };

    const appendResult = (value) => {
        const content = displayText(value);
        if (!content) return;
        updateConversation(activeIdRef.current, (conversation) => ({
            ...conversation,
            messages: [...conversation.messages, { id: generateId(), role: "assistant", content, streaming: false }],
        }));
    };

    useEffect(() => {
        let activeComponent = true;
        const socket = new WebSocket(socketUrl(mode));
        socketRef.current = socket;
        setStatus("connecting");

        socket.onopen = () => { if (activeComponent) setStatus("connected"); };
        socket.onmessage = (event) => {
            if (!activeComponent) return;
            let response;
            try { response = JSON.parse(event.data); }
            catch {
                const text = String(event.data || "");
                if (text === "__END_RESPONSE__") { setStreaming(false); finishAssistant(); }
                else if (text !== "Database Assistant Started!" && !text.startsWith("Type 'exit'")) appendChunk(text);
                return;
            }

            switch (response.type) {
                case "connected":
                    setStatus("connected");
                    setNotice(response.message || "Connected to Database Assistant.");
                    break;
                case "status":
                    setNotice(response.content || "");
                    break;
                case "chunk":
                    appendChunk(response.content || "");
                    break;
                case "interrupt":
                    setStreaming(false);
                    finishAssistant();
                    setInterrupt({ value: response.value });
                    setInterruptInput("");
                    setNotice("Human input is required before the agent can continue.");
                    break;
                case "result":
                    finishAssistant();
                    appendResult(response.data);
                    break;
                case "complete":
                    setStreaming(false);
                    finishAssistant();
                    setNotice("");
                    break;
                case "error":
                    setStreaming(false);
                    finishAssistant();
                    setNotice(response.message || "An unexpected backend error occurred.");
                    break;
                case "goodbye":
                    setStatus("disconnected");
                    setNotice(response.message || "Goodbye!");
                    break;
                default:
                    console.warn("Unknown WebSocket message", response);
            }
        };
        socket.onerror = () => {
            if (activeComponent) {
                setStatus("disconnected");
                setNotice("WebSocket connection failed. Confirm that the backend is running.");
            }
        };
        socket.onclose = () => {
            if (activeComponent) {
                setStatus("disconnected");
                setStreaming(false);
            }
        };
        return () => {
            activeComponent = false;
            if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) socket.close();
            socketRef.current = null;
        };
    }, [mode]);

    useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [active?.messages, streaming]);

    const newChat = () => {
        const conversation = createConversation();
        setConversations((items) => [conversation, ...items]);
        setActiveId(conversation.id);
        setInput("");
    };

    const sendMessage = () => {
        const text = input.trim();
        if (!text || streaming || interrupt) return;
        if (socketRef.current?.readyState !== WebSocket.OPEN) { setNotice("The backend is not connected."); return; }
        updateConversation(activeIdRef.current, (conversation) => ({
            ...conversation,
            title: conversation.messages.length ? conversation.title : `${text.slice(0, 40)}${text.length > 40 ? "..." : ""}`,
            messages: [...conversation.messages, { id: generateId(), role: "user", content: text, streaming: false }],
        }));
        socketRef.current.send(JSON.stringify({ type: "message", content: text }));
        setInput("");
        setStreaming(true);
        setNotice("Agent is working...");
    };

    const submitInterrupt = (value) => {
        if (socketRef.current?.readyState !== WebSocket.OPEN) { setNotice("The backend connection is unavailable."); return; }
        socketRef.current.send(JSON.stringify({ type: "resume", value }));
        setInterrupt(null);
        setInterruptInput("");
        setStreaming(true);
        setNotice("Resuming agent execution...");
    };

    const messages = active?.messages || [];
    const suggestions = ["Show all available tables", "Describe the employees schema", "Find the top five salaries", "Count employees by department"];

    return (
        <div className="app-shell">
            <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : "sidebar-closed"}`}>
                <div className="brand"><div className="brand-logo"><Database size={21} /></div><div className="brand-text"><strong>Database Copilot</strong><span>AI data assistant</span></div></div>
                <button type="button" className="new-chat-button" onClick={newChat}><Plus size={18} /><span>New chat</span></button>
                <div className="sidebar-label">Recent</div>
                <div className="conversation-list">
                    {conversations.map((conversation) => (
                        <button type="button" key={conversation.id} className={`conversation-button ${conversation.id === activeId ? "conversation-button-active" : ""}`} onClick={() => setActiveId(conversation.id)}>{conversation.title}</button>
                    ))}
                </div>
                <div className="connection-card">
                    {status === "connected" ? <Wifi size={17} className="connection-icon-connected" /> : <WifiOff size={17} className="connection-icon-disconnected" />}
                    <div><strong>{status === "connected" ? "Backend connected" : status === "connecting" ? "Connecting..." : "Disconnected"}</strong><span>FastAPI WebSocket</span></div>
                </div>
            </aside>

            <main className="main-content">
                <header className="topbar">
                    <div className="topbar-left">
                        <button type="button" className="icon-button" onClick={() => setSidebarOpen((value) => !value)}><Menu size={21} /></button>
                        <div className="agent-selector">
                            <button type="button" className={`agent-button ${mode === "chat" ? "agent-button-active" : ""}`} disabled={streaming || Boolean(interrupt)} onClick={() => setMode("chat")}><Sparkles size={17} /><span>Main Agent</span></button>
                            <button type="button" className={`agent-button agent-button-admin ${mode === "admin" ? "agent-button-active" : ""}`} disabled={streaming || Boolean(interrupt)} onClick={() => setMode("admin")}><ShieldCheck size={17} /><span>Admin Agent</span></button>
                        </div>
                    </div>
                    <div className={`status-pill status-${status}`}>{status === "connected" ? "Online" : status === "connecting" ? "Connecting" : "Offline"}</div>
                </header>

                <section className="chat-area">
                    <div className="chat-container">
                        {!messages.length ? (
                            <div className="welcome">
                                <div className="welcome-logo"><Database size={30} /></div>
                                <h1>How can I help with your data?</h1>
                                <p>Ask questions, inspect schemas, query records, or manage your database using the selected AI agent.</p>
                                <div className="suggestion-grid">{suggestions.map((suggestion) => <button type="button" key={suggestion} className="suggestion-button" onClick={() => setInput(suggestion)}>{suggestion}</button>)}</div>
                            </div>
                        ) : (
                            <div className="message-list">{messages.map((message) => <ChatMessage key={message.id} message={message} />)}</div>
                        )}
                        <div ref={bottomRef} />
                    </div>
                </section>

                <footer className="composer-area">
                    <div className="composer-container">
                        {notice && <div className="notice"><span>{notice}</span><button type="button" onClick={() => setNotice("")}><X size={15} /></button></div>}
                        <div className="composer">
                            <textarea value={input} rows={1} placeholder={`Message ${mode === "admin" ? "Admin Agent" : "Main Agent"}...`} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(); } }} />
                            {streaming ? (
                                <button type="button" className="send-button stop-button" title="Agent is running"><Square size={15} fill="currentColor" /></button>
                            ) : (
                                <button type="button" className="send-button" disabled={!input.trim() || status !== "connected" || Boolean(interrupt)} onClick={sendMessage}><Send size={18} /></button>
                            )}
                        </div>
                        <div className="composer-help">Enter to send · Shift + Enter for a new line</div>
                    </div>
                </footer>
            </main>

            <InterruptDialog request={interrupt} input={interruptInput} setInput={setInterruptInput} submit={submitInterrupt} />
        </div>
    );
}
