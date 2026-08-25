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

const END_RESPONSE = "__END_RESPONSE__";
const STATUS_PREFIX = "__STATUS__:";
const ERROR_PREFIX = "__ERROR__:";

let idCounter = 0;

function generateId() {
    idCounter += 1;

    return [
        Date.now(),
        idCounter,
        Math.random().toString(36).slice(2, 10),
    ].join("-");
}

function createConversation() {
    return {
        id: generateId(),
        title: "New database chat",
        messages: [],
    };
}

function getWebSocketUrl(mode) {
    const protocol =
        window.location.protocol === "https:" ? "wss:" : "ws:";

    return `${protocol}//${window.location.host}/${mode}`;
}

function ChatMessage({ message }) {
    const isUser = message.role === "user";

    return (
        <div
            className={`message-row ${isUser ? "message-row-user" : "message-row-assistant"
                }`}
        >
            {!isUser && (
                <div className="avatar avatar-assistant">
                    <Bot size={18} />
                </div>
            )}

            <div
                className={`message-bubble ${isUser ? "message-bubble-user" : "message-bubble-assistant"
                    }`}
            >
                <div className="message-content">
                    {message.content}
                </div>

                {message.streaming && (
                    <span className="streaming-cursor" />
                )}
            </div>

            {isUser && (
                <div className="avatar avatar-user">
                    <User size={18} />
                </div>
            )}
        </div>
    );
}

export default function App() {
    const initialConversationRef = useRef(createConversation());

    const [conversations, setConversations] = useState([
        initialConversationRef.current,
    ]);

    const [activeConversationId, setActiveConversationId] =
        useState(initialConversationRef.current.id);

    const [mode, setMode] = useState("chat");
    const [input, setInput] = useState("");
    const [connectionStatus, setConnectionStatus] =
        useState("connecting");

    const [isStreaming, setIsStreaming] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [notice, setNotice] = useState("");

    const socketRef = useRef(null);
    const bottomRef = useRef(null);
    const reconnectTimerRef = useRef(null);
    const intentionalCloseRef = useRef(false);
    const activeConversationIdRef = useRef(
        initialConversationRef.current.id
    );

    useEffect(() => {
        activeConversationIdRef.current = activeConversationId;
    }, [activeConversationId]);

    const activeConversation = useMemo(() => {
        return (
            conversations.find(
                (conversation) =>
                    conversation.id === activeConversationId
            ) ?? conversations[0]
        );
    }, [activeConversationId, conversations]);

    function updateConversation(conversationId, updater) {
        setConversations((currentConversations) =>
            currentConversations.map((conversation) =>
                conversation.id === conversationId
                    ? updater(conversation)
                    : conversation
            )
        );
    }

    function stopStreamingIndicator(conversationId) {
        updateConversation(conversationId, (conversation) => ({
            ...conversation,

            messages: conversation.messages.map(
                (message, index, messages) => {
                    const isLastMessage =
                        index === messages.length - 1;

                    if (
                        isLastMessage &&
                        message.role === "assistant"
                    ) {
                        return {
                            ...message,
                            streaming: false,
                        };
                    }

                    return message;
                }
            ),
        }));
    }

    useEffect(() => {
        let socket;
        let componentActive = true;

        function connectWebSocket() {
            if (!componentActive) {
                return;
            }

            if (
                socketRef.current &&
                (socketRef.current.readyState === WebSocket.OPEN ||
                    socketRef.current.readyState === WebSocket.CONNECTING)
            ) {
                return;
            }

            setConnectionStatus("connecting");
            intentionalCloseRef.current = false;

            const socketUrl = getWebSocketUrl(mode);

            try {
                socket = new WebSocket(socketUrl);
                socketRef.current = socket;
            } catch (error) {
                console.error("Unable to create WebSocket:", error);

                setConnectionStatus("disconnected");
                setNotice("Unable to create the WebSocket connection.");
                return;
            }

            socket.onopen = () => {
                if (!componentActive) {
                    return;
                }

                setConnectionStatus("connected");
                setNotice("Connected to Database Assistant.");
            };

            socket.onmessage = (event) => {
                if (!componentActive) {
                    return;
                }

                const chunk = String(event.data ?? "");

                if (
                    chunk === "Database Assistant Started!" ||
                    chunk.startsWith("Type 'exit'")
                ) {
                    return;
                }

                if (chunk === END_RESPONSE) {
                    setIsStreaming(false);

                    stopStreamingIndicator(
                        activeConversationIdRef.current
                    );

                    return;
                }

                if (chunk.startsWith(STATUS_PREFIX)) {
                    setNotice(chunk.slice(STATUS_PREFIX.length));
                    return;
                }

                if (chunk.startsWith(ERROR_PREFIX)) {
                    setNotice(chunk.slice(ERROR_PREFIX.length));
                    setIsStreaming(false);

                    stopStreamingIndicator(
                        activeConversationIdRef.current
                    );

                    return;
                }

                const conversationId =
                    activeConversationIdRef.current;

                updateConversation(
                    conversationId,
                    (conversation) => {
                        const messages = [...conversation.messages];
                        const lastMessage =
                            messages[messages.length - 1];

                        if (
                            lastMessage?.role === "assistant" &&
                            lastMessage.streaming
                        ) {
                            messages[messages.length - 1] = {
                                ...lastMessage,
                                content: lastMessage.content + chunk,
                            };
                        } else {
                            messages.push({
                                id: generateId(),
                                role: "assistant",
                                content: chunk,
                                streaming: true,
                            });
                        }

                        return {
                            ...conversation,
                            messages,
                        };
                    }
                );
            };

            socket.onerror = (event) => {
                console.error("WebSocket error:", event);

                if (!componentActive) {
                    return;
                }

                setNotice(
                    "WebSocket connection failed. Confirm FastAPI is running on port 8001."
                );
            };

            socket.onclose = () => {
                if (!componentActive) {
                    return;
                }

                socketRef.current = null;
                setConnectionStatus("disconnected");
                setIsStreaming(false);

                stopStreamingIndicator(
                    activeConversationIdRef.current
                );

                if (!intentionalCloseRef.current) {
                    setNotice(
                        "Connection lost. Attempting to reconnect..."
                    );

                    reconnectTimerRef.current = window.setTimeout(
                        connectWebSocket,
                        2500
                    );
                }
            };
        }

        connectWebSocket();

        return () => {
            componentActive = false;
            intentionalCloseRef.current = true;

            if (reconnectTimerRef.current) {
                window.clearTimeout(reconnectTimerRef.current);
            }

            if (
                socketRef.current &&
                socketRef.current.readyState !== WebSocket.CLOSED
            ) {
                socketRef.current.close();
            }

            socketRef.current = null;
        };
    }, [mode]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({
            behavior: "smooth",
        });
    }, [activeConversation?.messages, isStreaming]);

    function startNewConversation() {
        const conversation = createConversation();

        setConversations((currentConversations) => [
            conversation,
            ...currentConversations,
        ]);

        setActiveConversationId(conversation.id);
        setInput("");
        setNotice("");
    }

    function selectConversation(conversationId) {
        setActiveConversationId(conversationId);
        setInput("");
    }

    function changeMode(nextMode) {
        if (nextMode === mode) {
            return;
        }

        intentionalCloseRef.current = true;

        if (
            socketRef.current &&
            socketRef.current.readyState !== WebSocket.CLOSED
        ) {
            socketRef.current.close();
        }

        setIsStreaming(false);
        setMode(nextMode);

        setNotice(
            nextMode === "admin"
                ? "Admin Agent selected."
                : "Main Agent selected."
        );
    }

    function sendMessage() {
        const messageText = input.trim();

        if (!messageText || isStreaming) {
            return;
        }

        if (
            !socketRef.current ||
            socketRef.current.readyState !== WebSocket.OPEN
        ) {
            setNotice(
                "The assistant is not connected. Wait a moment and try again."
            );

            return;
        }

        const conversationId =
            activeConversationIdRef.current;

        updateConversation(conversationId, (conversation) => {
            const shouldUpdateTitle =
                conversation.messages.length === 0;

            return {
                ...conversation,

                title: shouldUpdateTitle
                    ? `${messageText.slice(0, 40)}${messageText.length > 40 ? "..." : ""
                    }`
                    : conversation.title,

                messages: [
                    ...conversation.messages,
                    {
                        id: generateId(),
                        role: "user",
                        content: messageText,
                        streaming: false,
                    },
                ],
            };
        });

        socketRef.current.send(messageText);

        setInput("");
        setIsStreaming(true);
        setNotice("Assistant is generating a response...");
    }

    function stopResponse() {
        intentionalCloseRef.current = true;

        if (
            socketRef.current &&
            socketRef.current.readyState !== WebSocket.CLOSED
        ) {
            socketRef.current.close();
        }

        setIsStreaming(false);

        stopStreamingIndicator(
            activeConversationIdRef.current
        );

        setNotice(
            "Response stopped. Switch agents or refresh the page to reconnect."
        );
    }

    function handleInputKeyDown(event) {
        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {
            event.preventDefault();
            sendMessage();
        }
    }

    const messages = activeConversation?.messages ?? [];

    const suggestedPrompts = [
        "Show all available tables",
        "Describe the employees schema",
        "Find the top five salaries",
        "Count employees by department",
    ];

    return (
        <div className="app-shell">
            <aside
                className={`sidebar ${sidebarOpen ? "sidebar-open" : "sidebar-closed"
                    }`}
            >
                <div className="brand">
                    <div className="brand-logo">
                        <Database size={21} />
                    </div>

                    <div className="brand-text">
                        <strong>Database Copilot</strong>
                        <span>AI data assistant</span>
                    </div>
                </div>

                <button
                    type="button"
                    className="new-chat-button"
                    onClick={startNewConversation}
                >
                    <Plus size={18} />
                    <span>New chat</span>
                </button>

                <div className="sidebar-label">Recent</div>

                <div className="conversation-list">
                    {conversations.map((conversation) => (
                        <button
                            type="button"
                            key={conversation.id}
                            className={`conversation-button ${conversation.id ===
                                    activeConversationId
                                    ? "conversation-button-active"
                                    : ""
                                }`}
                            onClick={() =>
                                selectConversation(conversation.id)
                            }
                        >
                            {conversation.title}
                        </button>
                    ))}
                </div>

                <div className="connection-card">
                    {connectionStatus === "connected" ? (
                        <Wifi
                            size={17}
                            className="connection-icon-connected"
                        />
                    ) : (
                        <WifiOff
                            size={17}
                            className="connection-icon-disconnected"
                        />
                    )}

                    <div>
                        <strong>
                            {connectionStatus === "connected"
                                ? "Backend connected"
                                : connectionStatus === "connecting"
                                    ? "Connecting..."
                                    : "Disconnected"}
                        </strong>

                        <span>FastAPI WebSocket</span>
                    </div>
                </div>
            </aside>

            <main className="main-content">
                <header className="topbar">
                    <div className="topbar-left">
                        <button
                            type="button"
                            className="icon-button"
                            aria-label="Toggle sidebar"
                            onClick={() =>
                                setSidebarOpen((current) => !current)
                            }
                        >
                            <Menu size={21} />
                        </button>

                        <div className="agent-selector">
                            <button
                                type="button"
                                className={`agent-button ${mode === "chat"
                                        ? "agent-button-active"
                                        : ""
                                    }`}
                                onClick={() => changeMode("chat")}
                            >
                                <Sparkles size={17} />
                                <span>Main Agent</span>
                            </button>

                            <button
                                type="button"
                                className={`agent-button agent-button-admin ${mode === "admin"
                                        ? "agent-button-active"
                                        : ""
                                    }`}
                                onClick={() => changeMode("admin")}
                            >
                                <ShieldCheck size={17} />
                                <span>Admin Agent</span>
                            </button>
                        </div>
                    </div>

                    <div
                        className={`status-pill status-${connectionStatus}`}
                    >
                        {connectionStatus === "connected"
                            ? "Online"
                            : connectionStatus === "connecting"
                                ? "Connecting"
                                : "Offline"}
                    </div>
                </header>

                <section className="chat-area">
                    <div className="chat-container">
                        {messages.length === 0 ? (
                            <div className="welcome">
                                <div className="welcome-logo">
                                    <Database size={30} />
                                </div>

                                <h1>How can I help with your data?</h1>

                                <p>
                                    Ask questions, inspect schemas, query
                                    records, or manage your database using
                                    the selected AI agent.
                                </p>

                                <div className="suggestion-grid">
                                    {suggestedPrompts.map((prompt) => (
                                        <button
                                            type="button"
                                            key={prompt}
                                            className="suggestion-button"
                                            onClick={() => setInput(prompt)}
                                        >
                                            {prompt}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        ) : (
                            <div className="message-list">
                                {messages.map((message) => (
                                    <ChatMessage
                                        key={message.id}
                                        message={message}
                                    />
                                ))}
                            </div>
                        )}

                        <div ref={bottomRef} />
                    </div>
                </section>

                <footer className="composer-area">
                    <div className="composer-container">
                        {notice && (
                            <div className="notice">
                                <span>{notice}</span>

                                <button
                                    type="button"
                                    aria-label="Dismiss notification"
                                    onClick={() => setNotice("")}
                                >
                                    <X size={15} />
                                </button>
                            </div>
                        )}

                        <div className="composer">
                            <textarea
                                value={input}
                                rows={1}
                                placeholder={`Message ${mode === "admin"
                                        ? "Admin Agent"
                                        : "Main Agent"
                                    }...`}
                                onChange={(event) =>
                                    setInput(event.target.value)
                                }
                                onKeyDown={handleInputKeyDown}
                            />

                            {isStreaming ? (
                                <button
                                    type="button"
                                    className="send-button stop-button"
                                    aria-label="Stop response"
                                    onClick={stopResponse}
                                >
                                    <Square
                                        size={15}
                                        fill="currentColor"
                                    />
                                </button>
                            ) : (
                                <button
                                    type="button"
                                    className="send-button"
                                    aria-label="Send message"
                                    disabled={
                                        !input.trim() ||
                                        connectionStatus !== "connected"
                                    }
                                    onClick={sendMessage}
                                >
                                    <Send size={18} />
                                </button>
                            )}
                        </div>

                        <div className="composer-help">
                            Enter to send · Shift + Enter for a new line
                        </div>
                    </div>
                </footer>
            </main>
        </div>
    );
}