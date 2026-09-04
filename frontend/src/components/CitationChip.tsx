"use client";

import React from "react";
import { SourceRef } from "@/types";
import { BookOpen } from "lucide-react";

interface CitationChipProps {
  source: SourceRef;
  onClick: (source: SourceRef) => void;
}

export const CitationChip: React.FC<CitationChipProps> = ({ source, onClick }) => {
  const pct = Math.round((source.score || 0) * 100);

  return (
    <button
      type="button"
      onClick={() => onClick(source)}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 hover:text-white border border-zinc-700/60 hover:border-amber-500/50 transition-all duration-150 shadow-xs cursor-pointer group"
      title={`Click to inspect chunk (${pct}% similarity match)`}
    >
      <BookOpen className="w-3 h-3 text-amber-400 group-hover:scale-110 transition-transform" />
      <span className="font-semibold text-zinc-200">{source.guest}</span>
      <span className="text-zinc-400">•</span>
      <span className="text-zinc-400">{source.timestamp}</span>
      <span className="ml-0.5 text-[10px] px-1.5 py-0.2 rounded-sm bg-zinc-900/90 text-amber-300 font-mono">
        {pct}%
      </span>
    </button>
  );
};
