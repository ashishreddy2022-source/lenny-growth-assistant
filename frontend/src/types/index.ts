export type LLMProvider = "ollama" | "claude" | "gemini";

export interface SourceRef {
  episode: string;
  guest: string;
  timestamp: string;
  score: number;
}

export interface CitationValidation {
  valid: boolean;
  has_citations: boolean;
  warning_badge: boolean;
  warning_message?: string | null;
}

export interface Artifact {
  id: string;
  message_id: string;
  artifact_type: "markdown" | "html";
  title: string;
  content: string;
  word_count_meta?: {
    word_count: number;
    target_words: number;
    in_tolerance: boolean;
    min_words: number;
    max_words: number;
    status: string;
  };
  created_at?: string;
}

export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
  is_out_of_domain?: boolean;
  citation_validation?: CitationValidation;
  artifact?: Artifact;
  created_at: string;
}

export interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ComponentHealth {
  status: "ok" | "degraded" | "down";
  details?: string;
  meta?: Record<string, any>;
}

export interface HealthStatus {
  status: "ok" | "degraded" | "down";
  components: {
    database: ComponentHealth;
    vector_index: ComponentHealth;
    ollama: ComponentHealth;
    claude: ComponentHealth;
    gemini: ComponentHealth;
  };
}
