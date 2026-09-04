"use client";

import React from "react";
import { SourceRef } from "@/types";
import { X, Sparkles, Clock, User, Headphones } from "lucide-react";

interface CitationModalProps {
  source: SourceRef | null;
  onClose: () => void;
}

export const CitationModal: React.FC<CitationModalProps> = ({ source, onClose }) => {
  if (!source) return null;

  const pct = Math.round((source.score || 0) * 100);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150">
      <div
        className="relative w-full max-w-lg p-6 bg-zinc-900 border border-zinc-700/80 rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between pb-4 border-b border-zinc-800">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider rounded-md bg-amber-500/20 text-amber-300 border border-amber-500/30">
                Grounding Source
              </span>
              <span className="text-xs text-zinc-400 font-mono">
                Similarity Match: <strong className="text-amber-400">{pct}%</strong>
              </span>
            </div>
            <h3 className="text-lg font-bold text-white leading-snug">
              {source.episode}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-zinc-400 hover:text-white rounded-lg hover:bg-zinc-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Metadata Details */}
        <div className="grid grid-cols-2 gap-3 py-4 text-sm">
          <div className="flex items-center gap-2 p-2.5 rounded-xl bg-zinc-950/60 border border-zinc-800">
            <User className="w-4 h-4 text-amber-400" />
            <div>
              <p className="text-[10px] uppercase text-zinc-500 font-semibold">Guest</p>
              <p className="font-medium text-zinc-200">{source.guest}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 p-2.5 rounded-xl bg-zinc-950/60 border border-zinc-800">
            <Clock className="w-4 h-4 text-amber-400" />
            <div>
              <p className="text-[10px] uppercase text-zinc-500 font-semibold">Timestamp</p>
              <p className="font-medium text-zinc-200">{source.timestamp}</p>
            </div>
          </div>
        </div>

        {/* Verification Note */}
        <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-200/90 flex items-start gap-2">
          <Sparkles className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <p>
            This segment was retrieved via <strong>pgvector HNSW cosine search</strong> directly from the public archive of Lenny's Podcast transcripts.
          </p>
        </div>

        {/* Action button */}
        <div className="mt-5 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-zinc-300 hover:text-white bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors cursor-pointer"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
