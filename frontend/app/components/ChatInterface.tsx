'use client';

import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ExportButtons from './ExportButtons';

interface Source {
    content: string;
    full_content?: string;
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
    const [useAgenticRAG, setUseAgenticRAG] = useState(true); // Toggle for Agentic RAG
    const [activeSource, setActiveSource] = useState<Source | null>(null);
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
            // Choose endpoint based on toggle (both now support streaming)
            const endpoint = useAgenticRAG ? '/chat/agentic/stream' : '/chat/stream';

            // Unified streaming logic for both modes
            const response = await fetch(`http://localhost:8000${endpoint}`, {
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

            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                buffer += chunk;

                // Split by double newline which is the standard SSE separator
                const lines = buffer.split('\n\n');

                // Keep the last part in the buffer as it might be incomplete
                buffer = lines.pop() || '';

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
                            } else if (data.type === 'done') {
                                // Stream finished signal
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
                                    <div id={`qa-pair-${index}`} className="msg-assistant w-full group/msg">
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
                                                        <div
                                                            key={idx}
                                                            onClick={() => setActiveSource(source)}
                                                            className="source-card group transition-all hover:-translate-y-1 cursor-pointer hover:shadow-md hover:border-[var(--accent-primary)]/30 active:scale-95"
                                                        >
                                                            <div className="font-semibold text-[var(--accent-secondary)] mb-1.5 truncate flex items-center gap-1">
                                                                <svg className="w-3 h-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>
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

                                        {/* Export Buttons */}
                                        {message.content && !isStreaming && (
                                            <ExportButtons
                                                question={messages[index - 1]?.content || ''}
                                                answer={message.content}
                                                answerId={`qa-pair-${index}`}
                                            />
                                        )}
                                    </div>
                                )}
                            </div>

                        ))}


                        <div ref={messagesEndRef} />
                    </div>
                )}
            </div>

            {/* RAG Mode Toggle - Minimalist top-right corner */}
            <div className="fixed top-6 right-6 z-50">
                <div className="flex items-center gap-2 text-[10px] text-[var(--text-tertiary)] select-none">
                    <button
                        onClick={() => setUseAgenticRAG(!useAgenticRAG)}
                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-all ${useAgenticRAG ? 'bg-[var(--accent-primary)]' : 'bg-gray-300'} hover:opacity-80`}
                        disabled={isLoading}
                        title={useAgenticRAG ? '当前：Agentic RAG' : '当前：传统 RAG'}
                    >
                        <span
                            className={`inline-block h-3 w-3 transform rounded-full bg-white shadow transition-transform ${useAgenticRAG ? 'translate-x-5' : 'translate-x-1'}`}
                        />
                    </button>
                    <span className={`transition-opacity ${useAgenticRAG ? 'opacity-100 font-semibold' : 'opacity-40'}`}>
                        🤖 Agentic
                    </span>
                </div>
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

            {/* Source Content Modal */}
            {
                activeSource && (
                    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 transition-all animate-in fade-in duration-200">
                        <div
                            className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col animate-in zoom-in-[0.98] duration-200 border border-white/20"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <div className="flex items-center justify-between p-4 border-b border-gray-100 bg-gray-50/50 rounded-t-xl">
                                <div className="flex flex-col gap-0.5 min-w-0">
                                    <h3 className="font-semibold text-base text-gray-800 truncate flex items-center gap-2">
                                        <svg className="w-4 h-4 text-[var(--accent-primary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                                        {activeSource.source}
                                    </h3>
                                    <div className="text-xs text-gray-500 font-mono flex items-center gap-2">
                                        <span className="bg-gray-200/60 px-1.5 py-0.5 rounded">Chunk {activeSource.chunk_id}</span>
                                        {activeSource.section && <span className="text-gray-400">|</span>}
                                        {activeSource.section && <span>{activeSource.section}</span>}
                                    </div>
                                </div>
                                <button
                                    onClick={() => setActiveSource(null)}
                                    className="p-2 hover:bg-gray-200/60 text-gray-400 hover:text-gray-600 rounded-lg transition-colors"
                                >
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                        <line x1="18" y1="6" x2="6" y2="18"></line>
                                        <line x1="6" y1="6" x2="18" y2="18"></line>
                                    </svg>
                                </button>
                            </div>
                            <div className="p-6 overflow-y-auto font-mono text-sm leading-relaxed text-gray-700 whitespace-pre-wrap bg-white selection:bg-[var(--accent-primary)]/10 selection:text-[var(--accent-primary)]">
                                {activeSource.full_content || activeSource.content}
                            </div>
                            <div className="p-3 border-t border-gray-100 bg-gray-50/50 rounded-b-xl flex justify-end">
                                <button
                                    onClick={() => setActiveSource(null)}
                                    className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-200/50 rounded-lg transition-colors"
                                >
                                    关闭预览
                                </button>
                            </div>
                        </div>
                        {/* Backdrop click to close */}
                        <div className="absolute inset-0 -z-10" onClick={() => setActiveSource(null)}></div>
                    </div>
                )
            }
        </div >
    );
}
