import "server-only";
import { cache } from "react";
import { createClient } from "@/lib/supabase/server";
import { DEFAULT_CONFIG, type ScoringConfig } from "@/lib/sentiment";

export type ActiveConfig = {
  id: string | null;
  version: number | null;
  key: string | null;
  name: string;
  config: ScoringConfig;
  /** false when `scoring_configs` is not there yet and the manager's original is in use. */
  fromDatabase: boolean;
};

const FALLBACK: ActiveConfig = {
  id: null,
  version: 1,
  key: "C0",
  name: DEFAULT_CONFIG.name ?? "Manager's original",
  config: DEFAULT_CONFIG,
  fromDatabase: false,
};

function looksLikeConfig(v: unknown): v is ScoringConfig {
  if (!v || typeof v !== "object") return false;
  const c = v as Record<string, unknown>;
  return !!(c.rating && c.approval && c.weights && c.bands && c.actions);
}

/** The one active scoring configuration (one per request, shared by every page). */
export const getActiveConfig = cache(async function getActiveConfig(): Promise<ActiveConfig> {
  try {
    const supabase = await createClient();
    const { data, error } = await supabase.from("scoring_configs").select("*").eq("status", "active").limit(1).maybeSingle();
    if (error || !data) return FALLBACK;
    const row = data as Record<string, unknown>;
    const config = row.config;
    if (!looksLikeConfig(config)) return FALLBACK;
    return {
      id: row.id == null ? null : String(row.id),
      version: row.version == null ? null : Number(row.version),
      key: row.key == null ? null : String(row.key),
      name: String(row.name ?? config.name ?? "Active configuration"),
      config,
      fromDatabase: true,
    };
  } catch {
    return FALLBACK;
  }
});
