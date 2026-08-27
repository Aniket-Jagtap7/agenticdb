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

function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
}

function cloneValue(value) {
    if (typeof globalThis.structuredClone === "function") {
        return globalThis.structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
}

function flattenToolArguments(value, parentPath = "", result = []) {
    if (!isPlainObject(value)) return result;

    Object.entries(value).forEach(([key, childValue]) => {
        const path = parentPath ? `${parentPath}.${key}` : key;

        if (isPlainObject(childValue)) {
            flattenToolArguments(childValue, path, result);
        } else {
            result.push({ path, label: key, value: childValue });
        }
    });

    return result;
}

function getValueAtPath(object, path) {
    return path.split(".").reduce(
        (current, key) => (current == null ? undefined : current[key]),
        object,
    );
}

function setValueAtPath(object, path, value) {
    const result = cloneValue(object);
    const keys = path.split(".");
    let current = result;

    keys.forEach((key, index) => {
        if (index === keys.length - 1) {
            current[key] = value;
            return;
        }

        if (!isPlainObject(current[key])) current[key] = {};
        current = current[key];
    });

    return result;
}

function convertEditedValue(enteredValue, originalValue) {
    if (typeof originalValue === "number") {
        const numberValue = Number(enteredValue);
        return Number.isNaN(numberValue) ? originalValue : numberValue;
    }

    if (typeof originalValue === "boolean") {
        return enteredValue === true || enteredValue === "true";
    }

    if (originalValue === null) return enteredValue === "" ? null : enteredValue;

    if (Array.isArray(originalValue)) {
        try {
            return JSON.parse(enteredValue);
        } catch {
            return originalValue;
        }
    }

    return enteredValue;
}

function humanizeFieldName(fieldName) {
    return fieldName
        .replaceAll("_", " ")
        .replace(/\b\w/g, (character) => character.toUpperCase());
}

function getInputType(fieldName, value) {
    const normalizedName = fieldName.toLowerCase();

    if (
        normalizedName.includes("date") &&
        typeof value === "string" &&
        /^\d{4}-\d{2}-\d{2}$/.test(value)
    ) {
        return "date";
    }

    if (typeof value === "number") return "number";
    return "text";
}

function ToolArgumentDisplay({ action }) {
    const fields = flattenToolArguments(action.args || {});

    if (!fields.length) {
        return <div className="tool-empty-arguments">No tool arguments were provided.</div>;
    }

    return (
        <div className="tool-arguments-display">
            {fields.map((field) => (
                <div className="tool-argument-row" key={field.path}>
                    <span className="tool-argument-name">
                        {humanizeFieldName(field.label)}
                    </span>
                    <span className="tool-argument-value" title={displayText(field.value)}>
                        {displayText(field.value)}
                    </span>
                </div>
            ))}
        </div>
    );
}

function ToolEditForm({ action, editedValues, onChange }) {
    const fields = flattenToolArguments(action.args || {});

    return (
        <div className="tool-edit-grid">
            {fields.map((field) => {
                const currentValue = editedValues[field.path] ?? "";
                const originalText = displayText(field.value);

                if (typeof field.value === "boolean") {
                    return (
                        <label className="tool-edit-field" key={field.path}>
                            <span className="tool-edit-label">
                                {humanizeFieldName(field.label)}
                            </span>
                            <select
                                value={currentValue}
                                title={`Current value: ${originalText}`}
                                onChange={(event) =>
                                    onChange(action.name, field.path, event.target.value)
                                }
                            >
                                <option value="">Keep current value</option>
                                <option value="true">True</option>
                                <option value="false">False</option>
                            </select>
                            <small>Current value: {originalText}</small>
                        </label>
                    );
                }

                return (
                    <label className="tool-edit-field" key={field.path}>
                        <span className="tool-edit-label">
                            {humanizeFieldName(field.label)}
                        </span>
                        <input
                            type={getInputType(field.label, field.value)}
                            value={currentValue}
                            placeholder={originalText}
                            title={`Current value: ${originalText}`}
                            onChange={(event) =>
                                onChange(action.name, field.path, event.target.value)
                            }
                        />
                        <small>Leave blank to keep: {originalText}</small>
                    </label>
                );
            })}
        </div>
    );
}

function InterruptDialog({ request, input, setInput, submit }) {
    const [selectedDecision, setSelectedDecision] = useState("");
    const [changedArguments, setChangedArguments] = useState({});

    useEffect(() => {
        setSelectedDecision("");
        setChangedArguments({});
        setInput("");
    }, [request, setInput]);

    if (!request) return null;

    const interruptValue = request.value;
    const isToolReview =
        isPlainObject(interruptValue) &&
        interruptValue.type === "tool_review" &&
        Array.isArray(interruptValue.actions);

    if (!isToolReview) {
        const title = interruptValue?.title || "Additional information required";
        const message =
            typeof interruptValue === "string"
                ? interruptValue
                : interruptValue?.message ||
                interruptValue?.prompt ||
                interruptValue?.question ||
                "The agent requires your input.";
        const placeholder =
            interruptValue?.placeholder || "Enter the requested details";

        const submitSimpleInput = () => {
            const enteredValue = input.trim();
            if (enteredValue) submit(enteredValue);
        };

        return (
            <div className="interrupt-overlay" role="dialog" aria-modal="true">
                <div className="interrupt-modal">
                    <div className="interrupt-header">
                        <div className="interrupt-icon"><ShieldCheck size={25} /></div>
                        <div><h2>{title}</h2><p>{message}</p></div>
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

    const actions = interruptValue.actions || [];

    function selectDecision(decision) {
        setSelectedDecision(decision);
        setInput("");
        if (decision !== "edit") setChangedArguments({});
    }

    function updateArgument(actionName, fieldPath, enteredValue) {
        setChangedArguments((current) => ({
            ...current,
            [actionName]: {
                ...(current[actionName] || {}),
                [fieldPath]: enteredValue,
            },
        }));
    }

    function createEditedActions() {
        return actions.map((action) => {
            const actionChanges = changedArguments[action.name] || {};
            let finalArguments = cloneValue(action.args || {});

            Object.entries(actionChanges).forEach(([fieldPath, enteredValue]) => {
                if (enteredValue === "" || enteredValue === undefined) return;

                const originalValue = getValueAtPath(action.args || {}, fieldPath);
                const convertedValue = convertEditedValue(enteredValue, originalValue);
                finalArguments = setValueAtPath(finalArguments, fieldPath, convertedValue);
            });

            return { action_name: action.name, args: finalArguments };
        });
    }

    function submitReview() {
        if (!selectedDecision) return;

        if (selectedDecision === "approve") {
            submit({ decision: "approve" });
            return;
        }

        if (selectedDecision === "respond" || selectedDecision === "reject") {
            const customMessage = input.trim();
            if (!customMessage) return;
            submit({ decision: selectedDecision, message: customMessage });
            return;
        }

        if (selectedDecision === "edit") {
            submit({ decision: "edit", edited_actions: createEditedActions() });
        }
    }

    const requiresCustomMessage =
        selectedDecision === "respond" || selectedDecision === "reject";
    const submitDisabled =
        !selectedDecision || (requiresCustomMessage && !input.trim());

    return (
        <div
            className="interrupt-overlay"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tool-review-title"
        >
            <div className="interrupt-modal tool-review-modal">
                <div className="interrupt-header">
                    <div className="interrupt-icon"><ShieldCheck size={25} /></div>
                    <div>
                        <h2 id="tool-review-title">
                            {interruptValue.title || "Human Review Required"}
                        </h2>
                        <p>
                            {interruptValue.message ||
                                "Review the following tool actions and provide your decision."}
                        </p>
                    </div>
                </div>

                {interruptValue.table && (
                    <div className="tool-target-table">
                        <span>Target table</span>
                        <strong>{interruptValue.table}</strong>
                    </div>
                )}

                <div className="tool-review-action-list">
                    {actions.map((action, actionIndex) => (
                        <section
                            className="tool-review-card"
                            key={`${action.name}-${actionIndex}`}
                        >
                            <div className="tool-review-card-header">
                                <div>
                                    <span className="tool-action-number">Action {actionIndex + 1}</span>
                                    <h3>{humanizeFieldName(action.name)}</h3>
                                </div>
                                <span className="tool-risk-badge">Risk review</span>
                            </div>

                            <div className="tool-risk-content">
                                {action.risk_analysis ||
                                    action.risk ||
                                    "Risk analysis unavailable."}
                            </div>

                            {selectedDecision === "edit" ? (
                                <>
                                    <h4 className="tool-section-title">Edit tool arguments</h4>
                                    <ToolEditForm
                                        action={action}
                                        editedValues={changedArguments[action.name] || {}}
                                        onChange={updateArgument}
                                    />
                                </>
                            ) : (
                                <>
                                    <h4 className="tool-section-title">Current tool arguments</h4>
                                    <ToolArgumentDisplay action={action} />
                                </>
                            )}
                        </section>
                    ))}
                </div>

                <div className="tool-decision-grid">
                    {[
                        ["approve", "Approve", "tool-approve-button"],
                        ["edit", "Edit", "tool-edit-button"],
                        ["respond", "Respond", "tool-respond-button"],
                        ["reject", "Reject", "tool-reject-button"],
                    ].map(([decision, label, className]) => (
                        <button
                            type="button"
                            key={decision}
                            className={`tool-decision-button ${className} ${selectedDecision === decision ? "tool-decision-selected" : ""
                                }`}
                            onClick={() => selectDecision(decision)}
                        >
                            {label}
                        </button>
                    ))}
                </div>

                {selectedDecision === "approve" && (
                    <div className="tool-decision-message tool-approve-message">
                        The displayed tool actions will be executed without changes.
                    </div>
                )}

                {selectedDecision === "edit" && (
                    <div className="tool-decision-message tool-edit-message">
                        Enter only values you want to change. Blank fields keep their current values.
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
                        placeholder="Enter the rejection reason"
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
