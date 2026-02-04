'use client';

import { useState, useEffect } from 'react';
import ChatInterface from './components/ChatInterface';

interface Conversation {
  id: string;
  title: string;
  updated_at: string;
}

export default function Home() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [history, setHistory] = useState<Conversation[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Fetch history
  const fetchHistory = async () => {
    try {
      const res = await fetch('http://localhost:8000/history');
      if (res.ok) {
        const data = await res.json();
        setHistory(data);
      }
    } catch (e) {
      console.error("Failed to fetch history", e);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [conversationId]); // Refresh when conversation changes

  const startNewChat = () => {
    setConversationId(null);
  };

  const deleteChat = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm('确定要删除这段对话吗？')) return;

    try {
      await fetch(`http://localhost:8000/history/${id}`, { method: 'DELETE' });
      fetchHistory();
      if (conversationId === id) {
        setConversationId(null);
      }
    } catch (e) {
      console.error("Failed to delete chat", e);
    }
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[var(--bg-primary)]">
      {/* Sidebar */}
      <aside
        className={`sidebar flex-shrink-0 flex flex-col transition-all duration-300 ${sidebarOpen ? 'w-[260px] translate-x-0' : 'w-0 -translate-x-full opacity-0'
          }`}
      >
        {/* Sidebar Header */}
        <div className="p-4 flex items-center justify-between border-b border-[var(--border-subtle)]">
          <div className="flex items-center gap-2 font-medium bg-gradient-to-r from-[var(--accent-primary)] to-[var(--accent-secondary)] bg-clip-text text-transparent">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent-primary)]">
              <path d="M12 2a10 10 0 1 0 10 10 4 4 0 0 1-5-5 4 4 0 0 1-5-5" />
              <path d="M8.5 8.5v.01" />
              <path d="M16 15.5v.01" />
              <path d="M12 12v.01" />
            </svg>
            <span>Digital Brain</span>
          </div>
        </div>

        {/* New Chat Button */}
        <div className="p-3">
          <button
            onClick={startNewChat}
            className="w-full flex items-center gap-2 px-3 py-2.5 bg-white border border-[var(--border-subtle)] rounded-lg shadow-sm hover:shadow-md hover:border-[var(--accent-light)] transition-all text-sm font-medium text-[var(--accent-primary)]"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
            开启新对话
          </button>
        </div>

        {/* History List */}
        <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
          <p className="px-3 py-1 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wider">
            History
          </p>
          {history.map((chat) => (
            <div
              key={chat.id}
              onClick={() => setConversationId(chat.id)}
              className={`group flex items-center justify-between px-3 py-2.5 rounded-lg text-sm cursor-pointer transition-colors ${conversationId === chat.id
                ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)] font-medium shadow-sm'
                : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]'
                }`}
            >
              <span className="truncate flex-1">{chat.title}</span>

              {/* Delete Button (visible on hover) */}
              <button
                onClick={(e) => deleteChat(e, chat.id)}
                className="opacity-0 group-hover:opacity-100 p-1 hover:bg-white rounded text-[var(--text-tertiary)] hover:text-red-500 transition-all"
                title="删除"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            </div>
          ))}
        </div>

        {/* User Footer */}
        <div className="p-4 border-t border-[var(--border-subtle)] text-xs text-[var(--text-tertiary)] flex items-center justify-between">
          <span>Pro Version</span>
          <div className="h-2 w-2 rounded-full bg-green-500"></div>
        </div>
      </aside>

      {/* Toggle Sidebar Button (absolute) */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className={`fixed top-4 z-40 p-2 rounded-lg text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] transition-all ${sidebarOpen ? 'left-[270px]' : 'left-4'
          }`}
      >
        {sidebarOpen ? (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <line x1="9" y1="3" x2="9" y2="21"></line>
          </svg>
        ) : (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <line x1="9" y1="3" x2="9" y2="21"></line>
          </svg>
        )}
      </button>

      {/* Main Chat Area */}
      <main className="flex-1 min-w-0 bg-white relative">
        <ChatInterface
          conversationId={conversationId}
          onConversationIdChange={setConversationId}
        />
      </main>
    </div>
  );
}
