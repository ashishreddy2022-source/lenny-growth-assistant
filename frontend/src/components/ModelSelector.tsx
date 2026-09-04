"use client";

import React, { useState } from "react";
import { ChevronDown, Cpu, Cloud, Check } from "lucide-react";
import { HealthStatus } from "@/types";

interface ModelSelectorProps {
  selectedProvider: "ollama" | "claude";
  onSelectProvider: (provider: "ollama" | "claude") => void;
  health: HealthStatus | null;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  selectedProvider,
  onSelectProvider,
  health,
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const ollamaStatus = health?.components?.ollama?.status || "down";
  const claudeStatus = health?.components?.claude?.status || "down";

  const getStatusBadge = (status: "ok" | "degraded" | "down") => {
    switch (status) {
      case "ok":
        return <span className="w-2 h-2 rounded-full bg-emerald-500 shadow-xs shadow-emerald-500/50" />;
      case "degraded":
        return <span className="w-2 h-2 rounded-full bg-amber-500 shadow-xs shadow-amber-500/50" />;
      default:
        return <span className="w-2 h-2 rounded-full bg-rose-500 shadow-xs shadow-rose-500/50" />;
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-zinc-900/90 hover:bg-zinc-800 border border-zinc-700/70 hover:border-zinc-600 transition-all text-xs font-medium text-zinc-200 shadow-xs cursor-pointer"
      >
        {selectedProvider === "ollama" ? (
          <Cpu className="w-3.5 h-3.5 text-amber-400" />
        ) : (
          <Cloud className="w-3.5 h-3.5 text-indigo-400" />
        )}
        <span className="font-semibold">
          {selectedProvider === "ollama" ? "Ollama (Local)" : "Claude 3.5 (Cloud)"}
        </span>
        {getStatusBadge(selectedProvider === "ollama" ? ollamaStatus : claudeStatus)}
        <ChevronDown className={`w-3 h-3 text-zinc-400 transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 mt-2 w-64 p-1.5 rounded-xl bg-zinc-900 border border-zinc-700 shadow-2xl z-50 animate-in fade-in zoom-in-95 duration-100">
            <div className="px-2.5 py-1.5 text-[10px] uppercase font-bold text-zinc-500 tracking-wider border-b border-zinc-800">
              Select Inference Provider
            </div>

            {/* Ollama Option */}
            <button
              type="button"
              onClick={() => {
                onSelectProvider("ollama");
                setIsOpen(false);
              }}
              className={`w-full flex items-center justify-between p-2.5 rounded-lg text-left text-xs transition-colors cursor-pointer ${
                selectedProvider === "ollama"
                  ? "bg-amber-500/10 text-amber-300 font-semibold border border-amber-500/20"
                  : "hover:bg-zinc-800 text-zinc-300"
              }`}
            >
              <div className="flex items-start gap-2.5">
                <Cpu className="w-4 h-4 text-amber-400 mt-0.5" />
                <div>
                  <div className="flex items-center gap-1.5">
                    <span>Ollama (Llama 3.2)</span>
                    {getStatusBadge(ollamaStatus)}
                  </div>
                  <p className="text-[11px] text-zinc-400 font-normal">
                    Private, zero-cost, local GPU
                  </p>
                </div>
              </div>
              {selectedProvider === "ollama" && <Check className="w-4 h-4 text-amber-400" />}
            </button>

            {/* Claude Option */}
            <button
              type="button"
              onClick={() => {
                onSelectProvider("claude");
                setIsOpen(false);
              }}
              className={`w-full flex items-center justify-between p-2.5 rounded-lg text-left text-xs transition-colors cursor-pointer mt-1 ${
                selectedProvider === "claude"
                  ? "bg-indigo-500/10 text-indigo-300 font-semibold border border-indigo-500/20"
                  : "hover:bg-zinc-800 text-zinc-300"
              }`}
            >
              <div className="flex items-start gap-2.5">
                <Cloud className="w-4 h-4 text-indigo-400 mt-0.5" />
                <div>
                  <div className="flex items-center gap-1.5">
                    <span>Claude 3.5 Sonnet</span>
                    {getStatusBadge(claudeStatus)}
                  </div>
                  <p className="text-[11px] text-zinc-400 font-normal">
                    Cloud reasoning, long context
                  </p>
                </div>
              </div>
              {selectedProvider === "claude" && <Check className="w-4 h-4 text-indigo-400" />}
            </button>
          </div>
        </>
      )}
    </div>
  );
};
