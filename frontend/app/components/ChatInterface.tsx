'use client';

import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Source {
    content: string;
    source: string;
    chunk_id: number;
    section: string;
}

interface Message {
    id?: number;
    role: 'user' | 'assistant';
    content: string;
    sources?: Source[];
}

interface ChatInterfaceProps {
    conversationId: string | null;
    onConversationIdChange: (id: string) => void;
}

export default function ChatInterface({ conversationId, onConversationIdChange }: ChatInterfaceProps) {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isStreaming, setIsStreaming] = useState(false); // Prevent message override during streaming
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Auto-resize textarea
    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto'; // Reset height
            textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
        }
    }, [input]);

    // Fetch messages when conversation ID changes (skip during streaming to prevent override)
    useEffect(() => {
        const fetchMessages = async () => {
            // Skip fetching during streaming - local state is authoritative
            if (isStreaming) {
                return;
            }

            if (!conversationId) {
                setMessages([]);
                return;
            }

            try {
                const res = await fetch(`http://localhost:8000/history/${conversationId}`);
                if (res.ok) {
                    const data = await res.json();
                    setMessages(data);
                }
            } catch (error) {
                console.error("Failed to load conversation", error);
            }
        };

        fetchMessages();
    }, [conversationId, isStreaming]);

    // Scroll to bottom on new messages
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, isLoading]);

    const handleSubmit = async (e?: React.FormEvent) => {
        e?.preventDefault();
        if (!input.trim() || isLoading) return;

        const currentInput = input;
        setInput('');
        if (textareaRef.current) textareaRef.current.style.height = 'auto'; // Reset height

        const userMessage: Message = { role: 'user', content: currentInput };
        setMessages(prev => [...prev, userMessage]);
        setIsLoading(true);
        setIsStreaming(true); // Prevent useEffect from overriding local messages

        try {
            // Streaming implementation
            const response = await fetch('http://localhost:8000/chat/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question: currentInput,
                    conversation_id: conversationId,
                }),
            });

            if (!response.ok) throw new Error('Failed to get response');

            const reader = response.body?.getReader();
            if (!reader) throw new Error('No reader available');

            const decoder = new TextDecoder();
            let assistantMessage: Message = { role: 'assistant', content: '', sources: [] };
            setMessages(prev => [...prev, assistantMessage]);

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));

                            if (data.type === 'metadata') {
                                assistantMessage.sources = data.sources;
                                if (data.conversation_id && !conversationId) {
                                    onConversationIdChange(data.conversation_id);
                                }
                            } else if (data.type === 'content') {
                                assistantMessage.content += data.content;
                            }

                            // Update UI
                            setMessages(prev => {
                                const newMessages = [...prev];
                                newMessages[newMessages.length - 1] = { ...assistantMessage };
                                return newMessages;
                            });
                        } catch (e) {
                            console.error('Error parsing SSE:', e);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Chat error:', error);
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: '⚠️ 网络连接错误，请检查后端服务。'
            }]);
        } finally {
            setIsLoading(false);
            setIsStreaming(false); // Allow history fetching again
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    return (
        <div className="flex flex-col h-full relative">
            {/* Messages Container - min-h-0 enables flex child scrolling, pb-52 for input area */}
            <div className="flex-1 min-h-0 overflow-y-auto pt-8 pb-52">
                {messages.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center px-6 animate-slide-up">
                        <div className="w-20 h-20 bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)] rounded-[2rem] flex items-center justify-center shadow-[var(--shadow-island)] mb-8">
                            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M12 2a10 10 0 1 0 10 10 4 4 0 0 1-5-5 4 4 0 0 1-5-5" />
                                <path d="M8.5 8.5v.01" />
                                <path d="M16 15.5v.01" />
                                <path d="M12 12v.01" />
                            </svg>
                        </div>
                        <h2 className="text-2xl font-semibold mb-3 text-[var(--text-primary)]">
                            有什么我可以帮您的吗？
                        </h2>
                        <p className="text-[var(--text-secondary)] max-w-md text-sm leading-relaxed">
                            我是您的数字后端助手。您可以问我关于 ICC2flow、时钟树综合 (CTS)、物理设计或任何技术文档的问题。
                        </p>
                    </div>
                ) : (
                    <div className="msg-container space-y-8">
                        {messages.map((message, index) => (
                            <div
                                key={index}
                                className={`flex flex-col animate-slide-up ${message.role === 'user' ? 'items-end' : 'items-start'}`}
                            >
                                {/* Role Label */}
                                <div className={`text-xs font-semibold mb-2 px-1 ${message.role === 'user' ? 'text-[var(--text-tertiary)]' : 'text-[var(--accent-primary)]'}`}>
                                    {message.role === 'user' ? 'YOU' : 'AI ASSISTANT'}
                                </div>

                                {message.role === 'user' ? (
                                    <div className="msg-user text-[15px] shadow-sm">
                                        <div className="whitespace-pre-wrap">{message.content}</div>
                                    </div>
                                ) : (
                                    <div className="msg-assistant w-full">
                                        <div className="prose prose-slate max-w-none">
                                            {message.content ? (
                                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                                            ) : (
                                                <div className="flex items-center gap-2 text-[var(--text-secondary)] py-2">
                                                    <span className="relative flex h-3 w-3">
                                                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--accent-primary)] opacity-75"></span>
                                                        <span className="relative inline-flex rounded-full h-3 w-3 bg-[var(--accent-primary)]"></span>
                                                    </span>
                                                    <span className="text-sm font-medium animate-pulse">思考中...</span>
                                                </div>
                                            )}
                                        </div>

                                        {/* Sources Island */}
                                        {message.sources && message.sources.length > 0 && (
                                            <div className="mt-6">
                                                <div className="flex items-center gap-2 mb-3 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wide">
                                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                                        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
                                                        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
                                                    </svg>
                                                    参考来源 ({message.sources.length})
                                                </div>
                                                <div className="flex gap-3 overflow-x-auto pb-4 -mx-4 px-4 scrollbar-hide">
                                                    {message.sources.map((source, idx) => (
                                                        <div key={idx} className="source-card group transition-all hover:-translate-y-1">
                                                            <div className="font-semibold text-[var(--accent-secondary)] mb-1.5 truncate">
                                                                {source.source.replace('.md', '').replace('.pdf', '')}
                                                            </div>
                                                            <div className="text-[var(--text-tertiary)] text-[10px] uppercase font-mono mb-2">
                                                                {source.section || `Chunk ${source.chunk_id}`}
                                                            </div>
                                                            <div className="text-[var(--text-secondary)] line-clamp-3 leading-relaxed">
                                                                {source.content}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}


                        <div ref={messagesEndRef} />
                    </div>
                )}
            </div>

            {/* Input Island - Fixed at bottom */}
            <div className="input-island-wrapper bg-gradient-to-t from-white via-white to-transparent pt-10 pb-8">
                <div className="input-island relative bg-white">
                    <textarea
                        ref={textareaRef}
                        rows={1}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="输入您的问题 (Shift + Enter 换行)..."
                        className="max-h-[200px] overflow-y-auto"
                        disabled={isLoading}
                    />
                    <div className="flex-shrink-0 pb-1">
                        <button
                            onClick={() => handleSubmit()}
                            disabled={isLoading || !input.trim()}
                            className="btn-send hover:shadow-lg disabled:bg-gray-200 disabled:text-gray-400"
                        >
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                <line x1="12" y1="19" x2="12" y2="5"></line>
                                <polyline points="5 12 12 5 19 12"></polyline>
                            </svg>
                        </button>
                    </div>
                </div>
                <div className="text-center mt-3 text-xs text-[var(--text-tertiary)] select-none">
                    AI 生成内容可能不完全准确，请核对重要信息。
                </div>
            </div>
        </div>
    );
}
