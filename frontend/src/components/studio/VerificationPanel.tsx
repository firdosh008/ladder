import { CheckCircle, XCircle, Info } from "@phosphor-icons/react";
import { cn } from "../../lib/cn";
import type { VerificationReport } from "../../lib/agents";

const verdictIcon = (verdict: string) => {
  if (verdict === "verified") return <CheckCircle className="w-4 h-4 text-emerald-500" />;
  if (verdict === "contradicted") return <XCircle className="w-4 h-4 text-red-500" />;
  return <Info className="w-4 h-4 text-zinc-400" />;
};

const verdictLabel = (verdict: string) => {
  if (verdict === "verified") return "Verified";
  if (verdict === "contradicted") return "Contradicted";
  return "Not checked";
};

const verdictColor = (verdict: string, isContextual?: boolean) => {
  if (verdict === "verified") return "bg-emerald-50 border-emerald-200 text-emerald-800";
  if (verdict === "contradicted") return "bg-red-50 border-red-200 text-red-800";
  if (isContextual) return "bg-zinc-50 border-zinc-200 text-zinc-500";
  return "bg-zinc-50 border-zinc-200 text-zinc-600";
};

type Props = {
  report: VerificationReport | null;
  stage?: "ideas" | "script" | "scene";
  loading?: boolean;
  loadingStage?: string;
};

export function VerificationPanel({ report, stage = "script", loading, loadingStage }: Props) {
  // Loading state — mini spinner while fact checker runs
  if (loading && !report) {
    const label = loadingStage === "searching" ? "Searching sources..." : `Checking ${stage} facts...`;
    return (
      <div className="mt-3 p-3 rounded-lg border bg-blue-50 border-blue-200">
        <div className="flex items-center gap-2 text-sm font-medium text-blue-700">
          <span className="inline-block w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
          {label}
        </div>
      </div>
    );
  }

  if (!report) return null;

  const r = report as VerificationReport;
  if (!r.claims || r.claims.length === 0) {
    return (
      <div className="mt-3 p-3 rounded-lg border bg-green-50 border-green-200">
        <div className="flex items-center gap-2 text-sm font-medium text-green-700">
          <CheckCircle className="w-4 h-4" />
          Fact check complete — no factual claims to verify
        </div>
      </div>
    );
  }

  // Split claims: core (verified/contradicted/unverifiable) vs contextual (not checked)
  const coreClaims = r.claims.filter(c => (c.claim as any).importance !== "contextual");
  const contextualClaims = r.claims.filter(c => (c.claim as any).importance === "contextual");

  const coreVerified = coreClaims.filter(c => c.verdict === "verified");
  const coreContradicted = coreClaims.filter(c => c.verdict === "contradicted");
  const coreUnverifiable = coreClaims.filter(c => c.verdict === "unverifiable");

  return (
    <div className="mt-3 space-y-2">
      {/* Summary bar — constructive framing */}
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg border bg-white text-sm flex-wrap">
        <Info className="w-4 h-4 text-zinc-500 shrink-0" />
        <span className="font-medium text-zinc-700">
          {stage === "ideas" ? "Idea" : "Script"} fact check
        </span>

        {coreVerified.length > 0 && (
          <>
            <span className="text-zinc-300">·</span>
            <span className="text-emerald-600 font-medium">
              {coreVerified.length} verified
            </span>
          </>
        )}

        {coreContradicted.length > 0 && (
          <>
            <span className="text-zinc-300">·</span>
            <span className="text-red-600 font-medium">
              {coreContradicted.length} contradicted
            </span>
          </>
        )}

        {coreUnverifiable.length > 0 && (
          <>
            <span className="text-zinc-300">·</span>
            <span className="text-zinc-500">
              {coreUnverifiable.length} could not verify
            </span>
          </>
        )}

        {contextualClaims.length > 0 && (
          <>
            <span className="text-zinc-300">·</span>
            <span className="text-zinc-400">
              {contextualClaims.length} illustrative
            </span>
          </>
        )}

        {coreClaims.length === 0 && contextualClaims.length > 0 && (
          <span className="text-zinc-400">— no core claims to verify</span>
        )}
      </div>

      {/* Core claim results */}
      {coreClaims.length > 0 && (
        <div className="space-y-1.5">
          {coreClaims.map((c, i) => (
            <details key={`core-${i}`} className="group">
              <summary className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer text-sm",
                verdictColor(c.verdict),
              )}>
                {verdictIcon(c.verdict)}
                <span className="flex-1 truncate">{c.claim.claim_text}</span>
                <span className="text-xs font-medium uppercase tracking-wide opacity-60">
                  {verdictLabel(c.verdict)}
                </span>
              </summary>
              <div className="px-3 py-2 ml-6 text-xs text-zinc-600 space-y-1 border-l-2 border-zinc-200 mb-1">
                {c.source_url && (
                  <div>
                    <span className="font-medium">Source: </span>
                    <a href={c.source_url} target="_blank" rel="noopener noreferrer"
                       className="text-blue-600 underline break-all">
                      {c.source_url}
                    </a>
                  </div>
                )}
                {c.supporting_text && (
                  <div>
                    <span className="font-medium">Evidence: </span>
                    <span>"{c.supporting_text}"</span>
                  </div>
                )}
                <div>
                  <span className="font-medium">Confidence: </span>
                  {(c.confidence * 100).toFixed(0)}%
                </div>
                <div>{c.explanation}</div>
              </div>
            </details>
          ))}
        </div>
      )}

      {/* Contextual claims — collapsed by default */}
      {contextualClaims.length > 0 && (
        <details className="text-xs text-zinc-400">
          <summary className="cursor-pointer hover:text-zinc-500 px-1">
            {contextualClaims.length} illustrative reference{contextualClaims.length !== 1 ? "s" : ""} (not fact-checked)
          </summary>
          <div className="mt-1 space-y-0.5 ml-4">
            {contextualClaims.map((c, i) => (
              <div key={`ctx-${i}`} className="text-zinc-400 truncate">
                "{c.claim.claim_text}"
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

