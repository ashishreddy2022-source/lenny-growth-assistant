"use client";

import React, { useMemo } from "react";
import DOMPurify from "dompurify";

interface SandboxedIframeProps {
  content: string;
  title?: string;
  className?: string;
}

/**
 * SandboxedIframe — Secure HTML artifact renderer.
 * 
 * SECURITY MANDATE (PRD.md §5 & Architecture.md §6):
 * - sandbox="allow-scripts" STRICTLY WITHOUT "allow-same-origin"
 * - Prevents executing scripts from accessing parent cookies, localStorage, or origin
 * - Runs DOMPurify sanitization on the input HTML before injecting into srcdoc
 */
export const SandboxedIframe: React.FC<SandboxedIframeProps> = ({
  content,
  title = "Artifact Preview",
  className = "w-full h-full min-h-[480px] border-0 rounded-lg bg-white",
}) => {
  const sanitizedDoc = useMemo(() => {
    // Sanitize markup using DOMPurify
    const cleanBody = DOMPurify.sanitize(content, {
      WHOLE_DOCUMENT: false,
      ADD_TAGS: ["style", "link"],
      ADD_ATTR: ["target"],
    });

    // Wrap in standard HTML5 skeleton with basic styling
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      padding: 1.5rem;
      margin: 0;
      color: #1a202c;
      background: #ffffff;
      line-height: 1.6;
    }
    img { max-width: 100%; height: auto; }
    pre { background: #f7fafc; padding: 1rem; border-radius: 0.375rem; overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
    th, td { border: 1px solid #e2e8f0; padding: 0.5rem 0.75rem; text-align: left; }
    th { background: #edf2f7; }
  </style>
</head>
<body>
  ${cleanBody}
</body>
</html>`;
  }, [content]);

  return (
    <iframe
      srcDoc={sanitizedDoc}
      title={title}
      // CRITICAL: sandbox="allow-scripts" WITHOUT allow-same-origin
      sandbox="allow-scripts"
      className={className}
      loading="lazy"
    />
  );
};
