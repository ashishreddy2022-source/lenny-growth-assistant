"use client";

import React, { useState, useRef, useEffect } from "react";
import { Message, SourceRef, HealthStatus, Artifact, LLMProvider } from "@/types";
import { ModelSelector } from "./ModelSelector";
import { CitationChip } from "./CitationChip";
import ReactMarkdown from "react-markdown";
import {
  Send,
  Sparkles,
  Bot,
  User,
  PanelLeft,
  FilePenLine,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Loader2,
  HelpCircle,
} from "lucide-react";

interface ChatPaneProps {
  messages: Message[];
  streamingToken: string;
  streamingStatus: string | null;
  streamingSources: SourceRef[];
  isStreaming: boolean;
  selectedProvider: LLMProvider;
  onSelectProvider: (provider: LLMProvider) => void;
  onSendMessage: (text: string, mode: "default" | "ship30") => void;
  onSelectSource: (source: SourceRef) => void;
  onSelectArtifact: (artifact: Artifact) => void;
  onToggleSidebar: () => void;
  health: HealthStatus | null;
  sessionTitle?: string;
}

const STARTER_PROMPTS = [
  {
    guest: "Brian Chesky",
    prompt: "How did Brian Chesky restructure product management at Airbnb?",
  },
  {
    guest: "Julie Zhuo",
    prompt: "What is Julie Zhuo's core advice on giving constructive feedback to managers?",
  },
  {
    guest: "Shreyas Doshi",
    prompt: "Explain Shreyas Doshi's distinction between execution and L1/L3 product strategy.",
  },
  {
    guest: "Gibson Biddle",
    prompt: "How does Gibson Biddle define the DHM (Delight, Hard-to-copy, Margin-enhancing) framework?",
  },
];

export const ChatPane: React.FC<ChatPaneProps> = ({
  messages,
  streamingToken,
  streamingStatus,
  streamingSources,
  isStreaming,
  selectedProvider,
  onSelectProvider,
  onSendMessage,
  onSelectSource,
  onSelectArtifact,
  onToggleSidebar,
  health,
  sessionTitle = "The Lenny Growth Assistant",
}) => {
  const [inputText, setInputText] = useState("");
  const [activeMode, setActiveMode] = useState<"default" | "ship30">("default");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll on message updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingToken, streamingStatus]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputText.trim() || isStreaming) return;
    onSendMessage(inputText.trim(), activeMode);
    setInputText("");
    if (activeMode === "ship30") {
      setActiveMode("default"); // Reset to default mode after requesting essay
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex flex-col h-full bg-zinc-950 text-zinc-100 overflow-hidden">
      {/* Top Navigation Bar */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-zinc-800/80 bg-zinc-900/40 backdrop-blur-md shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <button
            type="button"
            onClick={onToggleSidebar}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer"
            title="Toggle Sessions Sidebar"
          >
            <PanelLeft className="w-4 h-4" />
          </button>
          <div className="min-w-0">
            <h2 className="text-xs font-bold text-zinc-200 truncate">
              {sessionTitle}
            </h2>
            <span className="text-[10px] text-zinc-500 font-mono">
              Grounded in Lenny's Podcast
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <ModelSelector
            selectedProvider={selectedProvider}
            onSelectProvider={onSelectProvider}
            health={health}
          />
        </div>
      </header>

      {/* Message Stream */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
        {messages.length === 0 && !isStreaming ? (
          /* Empty State */
          <div className="flex flex-col items-center justify-center min-h-[60vh] max-w-xl mx-auto text-center space-y-6">
            <div className="w-12 h-12 rounded-2xl bg-linear-to-br from-amber-500 to-orange-600 flex items-center justify-center text-white shadow-xl shadow-amber-500/20">
              <Sparkles className="w-6 h-6" />
            </div>

            <div className="space-y-2">
              <h2 className="text-xl font-bold tracking-tight text-white">
                How can Lenny's guests help you grow?
              </h2>
              <p className="text-xs text-zinc-400 max-w-md mx-auto leading-relaxed">
                Query tactical advice from operators at Airbnb, Notion, Stripe, and Figma. Every answer is cited directly to podcast transcripts.
              </p>
            </div>

            {/* Starter Prompt Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 w-full text-left pt-2">
              {STARTER_PROMPTS.map((item, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onSendMessage(item.prompt, "default")}
                  className="p-3.5 rounded-xl bg-zinc-900/70 hover:bg-zinc-800/90 border border-zinc-800/90 hover:border-amber-500/40 transition-all text-left group cursor-pointer"
                >
                  <span className="text-[10px] font-bold uppercase tracking-wider text-amber-400/90">
                    {item.guest}
                  </span>
                  <p className="text-xs font-medium text-zinc-300 group-hover:text-white mt-1 leading-snug">
                    {item.prompt}
                  </p>
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg) => {
            const isUser = msg.role === "user";

            return (
              <div
                key={msg.id}
                className={`flex gap-3 max-w-3xl ${isUser ? "ml-auto justify-end" : "mr-auto"}`}
              >
                {!isUser && (
                  <div className="w-7 h-7 rounded-lg bg-zinc-800 border border-zinc-700/60 flex items-center justify-center shrink-0 text-amber-400 mt-1">
                    <Bot className="w-4 h-4" />
                  </div>
                )}

                <div
                  className={`flex flex-col space-y-2.5 max-w-[88%] ${
                    isUser
                      ? "bg-amber-600/20 border border-amber-500/30 text-zinc-100 rounded-2xl rounded-tr-xs px-4 py-3 text-sm shadow-xs"
                      : msg.is_out_of_domain
                      ? "bg-zinc-900/60 border border-zinc-800 text-zinc-400 rounded-2xl rounded-tl-xs px-4 py-3.5 text-sm"
                      : "bg-zinc-900/80 border border-zinc-800/80 text-zinc-200 rounded-2xl rounded-tl-xs px-5 py-4 text-sm shadow-md"
                  }`}
                >
                  {/* Out of Domain Notice */}
                  {msg.is_out_of_domain && (
                    <div className="flex items-center gap-1.5 text-xs text-amber-400/90 font-medium pb-1">
                      <HelpCircle className="w-3.5 h-3.5" />
                      <span>Out-of-Domain Query</span>
                    </div>
                  )}

                  {/* Message Content */}
                  <div className="prose prose-invert prose-zinc max-w-none text-sm leading-relaxed prose-p:my-1.5 prose-headings:my-2 prose-ul:my-1.5">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>

                  {/* Grounded Citation Chips */}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="pt-2 border-t border-zinc-800/70">
                      <div className="text-[10px] uppercase font-bold text-zinc-500 tracking-wider mb-1.5">
                        Grounded Sources ({msg.sources.length})
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {msg.sources.map((src, idx) => (
                          <CitationChip
                            key={idx}
                            source={src}
                            onClick={onSelectSource}
                          />
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Citation Validation Warning Badge */}
                  {!isUser && msg.citation_validation?.warning_badge && (
                    <div className="flex items-center gap-1.5 text-[11px] text-amber-400/90 bg-amber-500/10 px-2.5 py-1 rounded-md border border-amber-500/20 mt-1">
                      <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                      <span>{msg.citation_validation.warning_message || "Citation verification alert."}</span>
                    </div>
                  )}

                  {/* Artifact Badge or Ship 30 Trigger */}
                  {!isUser && !msg.is_out_of_domain && (
                    <div className="flex items-center gap-2 pt-2 text-xs">
                      {msg.artifact ? (
                        <button
                          type="button"
                          onClick={() => onSelectArtifact(msg.artifact!)}
                          className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 transition-colors font-semibold cursor-pointer"
                        >
                          <FileText className="w-3.5 h-3.5" />
                          <span>View Artifact: {msg.artifact.title}</span>
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onSendMessage(`Transform the above answer into a Ship 30 essay: ${msg.content.slice(0, 100)}...`, "ship30")}
                          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border border-zinc-700/60 transition-colors text-xs font-medium cursor-pointer"
                          title="Generate a Ship 30 for 30 essay using these exact retrieved sources"
                        >
                          <FilePenLine className="w-3.5 h-3.5 text-amber-400" />
                          <span>✎ Ship 30</span>
                        </button>
                      )}
                    </div>
                  )}
                </div>

                {isUser && (
                  <div className="w-7 h-7 rounded-lg bg-amber-600/30 border border-amber-500/40 flex items-center justify-center shrink-0 text-amber-300 mt-1">
                    <User className="w-4 h-4" />
                  </div>
                )}
              </div>
            );
          })
        )}

        {/* Streaming In-Progress Message */}
        {isStreaming && (
          <div className="flex gap-3 max-w-3xl mr-auto">
            <div className="w-7 h-7 rounded-lg bg-zinc-800 border border-zinc-700/60 flex items-center justify-center shrink-0 text-amber-400 mt-1 animate-pulse">
              <Bot className="w-4 h-4" />
            </div>

            <div className="flex flex-col space-y-2.5 max-w-[88%] bg-zinc-900/80 border border-zinc-800/80 text-zinc-200 rounded-2xl rounded-tl-xs px-5 py-4 text-sm shadow-md">
              {/* Status Header */}
              {streamingStatus && (
                <div className="flex items-center gap-2 text-xs text-amber-400 font-medium animate-pulse pb-1">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>
                    {streamingStatus === "retrieving"
                      ? "Searching podcast transcripts..."
                      : streamingStatus === "generating"
                      ? "Synthesizing answer..."
                      : "Processing..."}
                  </span>
                </div>
              )}

              {/* Streaming Content */}
              {streamingToken ? (
                <div className="prose prose-invert prose-zinc max-w-none text-sm leading-relaxed">
                  <ReactMarkdown>{streamingToken}</ReactMarkdown>
                </div>
              ) : (
                <div className="space-y-2 py-1">
                  <div className="h-3 w-48 bg-zinc-800 rounded animate-pulse" />
                  <div className="h-3 w-64 bg-zinc-800/60 rounded animate-pulse" />
                </div>
              )}

              {/* Streamed Sources */}
              {streamingSources.length > 0 && (
                <div className="pt-2 border-t border-zinc-800/70">
                  <div className="text-[10px] uppercase font-bold text-zinc-500 tracking-wider mb-1.5">
                    Retrieved Sources ({streamingSources.length})
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {streamingSources.map((src, idx) => (
                      <CitationChip
                        key={idx}
                        source={src}
                        onClick={onSelectSource}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Form */}
      <div className="p-4 border-t border-zinc-800/80 bg-zinc-900/30">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto space-y-2">
          {/* Mode Switcher Pill */}
          <div className="flex items-center justify-between text-xs px-1">
            <div className="flex items-center gap-1 p-0.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <button
                type="button"
                onClick={() => setActiveMode("default")}
                className={`px-2.5 py-1 rounded-md transition-colors cursor-pointer ${
                  activeMode === "default"
                    ? "bg-zinc-800 text-white font-semibold"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                Grounded Q&A
              </button>
              <button
                type="button"
                onClick={() => setActiveMode("ship30")}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-md transition-colors cursor-pointer ${
                  activeMode === "ship30"
                    ? "bg-amber-500 text-zinc-950 font-bold"
                    : "text-zinc-400 hover:text-amber-300"
                }`}
              >
                <FilePenLine className="w-3.5 h-3.5" />
                <span>Ship 30 Essay</span>
              </button>
            </div>

            <span className="text-[11px] text-zinc-500">
              Press <kbd className="px-1 py-0.5 rounded bg-zinc-800 text-zinc-400 font-mono text-[10px]">Enter</kbd> to send
            </span>
          </div>

          {/* Textarea and Send Button */}
          <div className="relative flex items-center">
            <textarea
              ref={textareaRef}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                activeMode === "ship30"
                  ? "Enter topic to write a ~1,250-word Ship 30 essay (e.g. 'How to structure PLG funnels')..."
                  : "Ask anything about product management, growth, or strategy..."
              }
              rows={2}
              className="w-full resize-none p-3.5 pr-14 rounded-xl bg-zinc-900 border border-zinc-700/80 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 text-sm text-zinc-100 placeholder-zinc-500 transition-colors"
            />
            <button
              type="submit"
              disabled={!inputText.trim() || isStreaming}
              className="absolute right-3 p-2 rounded-lg bg-amber-500 hover:bg-amber-400 disabled:bg-zinc-800 disabled:text-zinc-600 text-zinc-950 transition-colors cursor-pointer disabled:cursor-not-allowed shadow-md shadow-amber-500/10"
              title="Send Message"
            >
              {isStreaming ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
