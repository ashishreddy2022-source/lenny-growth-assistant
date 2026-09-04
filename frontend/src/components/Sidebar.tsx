"use client";

import React from "react";
import { Session, HealthStatus } from "@/types";
import { Plus, MessageSquare, Trash2, Database, Sparkles, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";

interface SidebarProps {
  sessions: Session[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onDeleteSession: (id: string) => void;
  health: HealthStatus | null;
}

export const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  health,
}) => {
  const getHealthIcon = (status?: string) => {
    switch (status) {
      case "ok":
        return <CheckCircle2 className="w-3 h-3 text-emerald-400" />;
      case "degraded":
        return <AlertTriangle className="w-3 h-3 text-amber-400" />;
      default:
        return <XCircle className="w-3 h-3 text-rose-400" />;
    }
  };

  return (
    <div className="flex flex-col h-full bg-zinc-950 border-r border-zinc-800/80 text-zinc-300 w-64 select-none">
      {/* Brand & New Chat */}
      <div className="p-4 border-b border-zinc-800/80">
        <div className="flex items-center gap-2.5 mb-4">
          <div className="w-7 h-7 rounded-lg bg-linear-to-br from-amber-500 to-orange-600 flex items-center justify-center text-white shadow-md shadow-amber-500/20">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h1 className="text-xs font-bold text-white tracking-tight">
              The Lenny Growth Assistant
            </h1>
            <p className="text-[10px] text-zinc-500 font-mono">Podcast Knowledge RAG</p>
          </div>
        </div>

        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-zinc-950 font-bold text-xs shadow-md shadow-amber-500/10 transition-colors cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          <span>New Chat</span>
        </button>
      </div>

      {/* Sessions List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-zinc-500">
          Chat History
        </div>

        {sessions.length === 0 ? (
          <div className="p-3 text-center text-xs text-zinc-500 italic">
            No previous sessions
          </div>
        ) : (
          sessions.map((s) => {
            const isActive = s.id === activeSessionId;
            return (
              <div
                key={s.id}
                onClick={() => onSelectSession(s.id)}
                className={`group flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-colors cursor-pointer ${
                  isActive
                    ? "bg-zinc-800 text-white font-semibold"
                    : "hover:bg-zinc-900 text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <div className="flex items-center gap-2 min-w-0 pr-2">
                  <MessageSquare className={`w-3.5 h-3.5 shrink-0 ${isActive ? "text-amber-400" : "text-zinc-500"}`} />
                  <span className="truncate">{s.title || "Untitled Chat"}</span>
                </div>

                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteSession(s.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 text-zinc-500 hover:text-rose-400 rounded transition-opacity"
                  title="Delete Session"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* System Health Footer */}
      <div className="p-3 border-t border-zinc-800/80 bg-zinc-900/30 text-[11px] space-y-1.5">
        <div className="flex items-center justify-between text-zinc-400">
          <div className="flex items-center gap-1.5">
            <Database className="w-3.5 h-3.5 text-zinc-400" />
            <span>PostgreSQL & Vectors</span>
          </div>
          {getHealthIcon(health?.components?.vector_index?.status)}
        </div>

        <div className="flex items-center justify-between text-zinc-400">
          <span>Ollama Daemon</span>
          {getHealthIcon(health?.components?.ollama?.status)}
        </div>

        <div className="flex items-center justify-between text-zinc-400">
          <span>Claude API</span>
          {getHealthIcon(health?.components?.claude?.status)}
        </div>
      </div>
    </div>
  );
};
