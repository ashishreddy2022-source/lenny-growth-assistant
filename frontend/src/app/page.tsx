"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Message, Session, SourceRef, Artifact, HealthStatus } from "@/types";
import { Sidebar } from "@/components/Sidebar";
import { ChatPane } from "@/components/ChatPane";
import { ArtifactViewer } from "@/components/ArtifactViewer";
import { CitationModal } from "@/components/CitationModal";

export default function Home() {
  // Session State
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionTitle, setSessionTitle] = useState<string>("The Lenny Growth Assistant");

  // Provider State
  const [selectedProvider, setSelectedProvider] = useState<"ollama" | "claude">("ollama");

  // Streaming State
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingToken, setStreamingToken] = useState("");
  const [streamingStatus, setStreamingStatus] = useState<string | null>(null);
  const [streamingSources, setStreamingSources] = useState<SourceRef[]>([]);

  // Artifact Viewer & Citation Modal State
  const [activeArtifact, setActiveArtifact] = useState<Artifact | null>(null);
  const [isArtifactOpen, setIsArtifactOpen] = useState(false);
  const [selectedSourceModal, setSelectedSourceModal] = useState<SourceRef | null>(null);

  // Layout State
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // Health Status
  const [health, setHealth] = useState<HealthStatus | null>(null);

  // 1. Fetch Health Status
  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch("/api/health");
      if (res.ok) {
        const data = await res.json();
        setHealth(data);
      }
    } catch {
      // Backend offline or unreachable
      setHealth(null);
    }
  }, []);

  // 2. Fetch Sessions
  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch("/api/sessions");
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
        if (data.length > 0 && !activeSessionId) {
          setActiveSessionId(data[0].id);
          setSessionTitle(data[0].title || "The Lenny Growth Assistant");
        }
      }
    } catch (err) {
      console.error("Failed to load sessions:", err);
    }
  }, [activeSessionId]);

  // 3. Fetch Messages for Active Session
  const fetchMessages = useCallback(async (id: string) => {
    try {
      const res = await fetch(`/api/sessions/${id}/messages`);
      if (res.ok) {
        const data: Message[] = await res.json();
        setMessages(data);

        // If latest message has an artifact, open it
        const lastWithArtifact = [...data].reverse().find((m) => m.artifact);
        if (lastWithArtifact && lastWithArtifact.artifact) {
          setActiveArtifact(lastWithArtifact.artifact);
          setIsArtifactOpen(true);
        }
      }
    } catch (err) {
      console.error("Failed to load messages:", err);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    fetchSessions();
    const interval = setInterval(fetchHealth, 15000);
    return () => clearInterval(interval);
  }, [fetchHealth, fetchSessions]);

  useEffect(() => {
    if (activeSessionId) {
      fetchMessages(activeSessionId);
      const current = sessions.find((s) => s.id === activeSessionId);
      if (current) setSessionTitle(current.title || "The Lenny Growth Assistant");
    } else {
      setMessages([]);
      setSessionTitle("The Lenny Growth Assistant");
    }
  }, [activeSessionId, fetchMessages, sessions]);

  // Handle New Chat
  const handleNewChat = () => {
    setActiveSessionId(null);
    setMessages([]);
    setActiveArtifact(null);
    setIsArtifactOpen(false);
    setSessionTitle("New Chat");
  };

  // Handle Delete Session
  const handleDeleteSession = async (id: string) => {
    try {
      await fetch(`/api/sessions/${id}`, { method: "DELETE" });
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (activeSessionId === id) {
        handleNewChat();
      }
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  };

  // Handle Send Message & SSE Streaming
  const handleSendMessage = async (text: string, mode: "default" | "ship30" = "default") => {
    if (isStreaming) return;

    // Optimistically append user message
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      session_id: activeSessionId || "",
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    setIsStreaming(true);
    setStreamingToken("");
    setStreamingStatus("retrieving");
    setStreamingSources([]);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-LLM-Provider": selectedProvider,
        },
        body: JSON.stringify({
          session_id: activeSessionId,
          message: text,
          mode: mode,
          provider: selectedProvider,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`Chat API error: HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let accumulatedToken = "";
      let currentSources: SourceRef[] = [];
      let finalMessageId: string | null = null;
      let finalSessionId: string | null = null;
      let isOutOfDomain = false;
      let citationVal = undefined;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const block of lines) {
          const rawLines = block.split("\n");
          let eventType = "message";
          let eventData = "";

          for (const line of rawLines) {
            if (line.startsWith("event: ")) {
              eventType = line.replace("event: ", "").trim();
            } else if (line.startsWith("data: ")) {
              eventData = line.replace("data: ", "").trim();
            }
          }

          if (!eventData) continue;

          try {
            const parsed = JSON.parse(eventData);

            if (eventType === "status") {
              setStreamingStatus(parsed.status);
            } else if (eventType === "sources") {
              currentSources = parsed.sources || [];
              setStreamingSources(currentSources);
            } else if (eventType === "token") {
              accumulatedToken += parsed.token || "";
              setStreamingToken(accumulatedToken);
            } else if (eventType === "artifact") {
              const art: Artifact = {
                id: parsed.id,
                message_id: parsed.message_id,
                artifact_type: parsed.artifact_type,
                title: parsed.title,
                content: parsed.content,
                word_count_meta: parsed.word_count_meta,
              };
              setActiveArtifact(art);
              setIsArtifactOpen(true);
            } else if (eventType === "done") {
              finalMessageId = parsed.message_id;
              finalSessionId = parsed.session_id;
              isOutOfDomain = !!parsed.is_out_of_domain;
              citationVal = parsed.citation_validation;
            } else if (eventType === "error") {
              accumulatedToken += `\n\n*(Error: ${parsed.error})*`;
              setStreamingToken(accumulatedToken);
            }
          } catch {
            // Ignore partial SSE parsing
          }
        }
      }

      // Finalize assistant message in message state
      const assistantMsg: Message = {
        id: finalMessageId || `assistant-${Date.now()}`,
        session_id: finalSessionId || activeSessionId || "",
        role: "assistant",
        content: accumulatedToken,
        sources: currentSources,
        is_out_of_domain: isOutOfDomain,
        citation_validation: citationVal,
        artifact: activeArtifact || undefined,
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMsg]);

      // If new session was spawned on server
      if (finalSessionId && finalSessionId !== activeSessionId) {
        setActiveSessionId(finalSessionId);
        fetchSessions();
      }
    } catch (err: any) {
      console.error("Streaming error:", err);
      const errorMsg: Message = {
        id: `err-${Date.now()}`,
        session_id: activeSessionId || "",
        role: "assistant",
        content: `Error connecting to Assistant: ${err.message}. Ensure backend is running.`,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsStreaming(false);
      setStreamingToken("");
      setStreamingStatus(null);
      setStreamingSources([]);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-zinc-950 font-sans antialiased">
      {/* Sidebar: Chat History & Health */}
      {isSidebarOpen && (
        <aside className="shrink-0 z-30">
          <Sidebar
            sessions={sessions}
            activeSessionId={activeSessionId}
            onSelectSession={(id) => setActiveSessionId(id)}
            onNewChat={handleNewChat}
            onDeleteSession={handleDeleteSession}
            health={health}
          />
        </aside>
      )}

      {/* Main Dual-Pane Area */}
      <main className="flex-1 flex min-w-0 h-full overflow-hidden relative">
        {/* Left Pane: Chat (55% desktop when artifact open, 100% otherwise) */}
        <section
          className={`h-full flex flex-col transition-all duration-300 ${
            isArtifactOpen ? "w-full lg:w-[55%]" : "w-full"
          }`}
        >
          <ChatPane
            messages={messages}
            streamingToken={streamingToken}
            streamingStatus={streamingStatus}
            streamingSources={streamingSources}
            isStreaming={isStreaming}
            selectedProvider={selectedProvider}
            onSelectProvider={setSelectedProvider}
            onSendMessage={handleSendMessage}
            onSelectSource={(source) => setSelectedSourceModal(source)}
            onSelectArtifact={(artifact) => {
              setActiveArtifact(artifact);
              setIsArtifactOpen(true);
            }}
            onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
            health={health}
            sessionTitle={sessionTitle}
          />
        </section>

        {/* Right Pane: Artifact Viewer (45% desktop, slide-over overlay on mobile/tablet) */}
        {isArtifactOpen && (
          <aside className="fixed inset-y-0 right-0 z-40 w-full lg:static lg:w-[45%] h-full shrink-0 shadow-2xl transition-all duration-300">
            <ArtifactViewer
              artifact={activeArtifact}
              onClose={() => setIsArtifactOpen(false)}
            />
          </aside>
        )}
      </main>

      {/* Modal for Inspecting Clicked Citation Chunk */}
      <CitationModal
        source={selectedSourceModal}
        onClose={() => setSelectedSourceModal(null)}
      />
    </div>
  );
}
