import { Clock } from "lucide-react";

export type TimezoneMode = "UTC" | "IST" | "LOCAL";

interface TimezoneSelectorProps {
  mode: TimezoneMode;
  onChange: (mode: TimezoneMode) => void;
}

export function TimezoneSelector({ mode, onChange }: TimezoneSelectorProps) {
  return (
    <div className="flex items-center gap-2 bg-black/40 border border-white/10 rounded-full px-3 py-1 backdrop-blur-md">
      <Clock size={14} className="text-cyan-400" />
      <div className="flex gap-1 text-[10px] font-bold tracking-tighter">
        {(["UTC", "IST", "LOCAL"] as TimezoneMode[]).map((m) => (
          <button
            key={m}
            onClick={() => onChange(m)}
            className={`px-2 py-0.5 rounded-full transition-all ${
              mode === m
                ? "bg-cyan-500 text-black"
                : "text-dim hover:text-white"
            }`}
          >
            {m}
          </button>
        ))}
      </div>
    </div>
  );
}

export function formatTimestamp(ts: string, mode: TimezoneMode): string {
  const date = new Date(ts);

  if (mode === "UTC") {
    return date.toISOString().replace("T", " ").substring(0, 19) + "Z";
  }

  if (mode === "IST") {
    // IST is UTC + 5:30
    const istOffset = 5.5 * 60 * 60 * 1000;
    const istDate = new Date(date.getTime() + istOffset);
    return istDate.toISOString().replace("T", " ").substring(0, 19) + " IST";
  }

  // Local
  return date.toLocaleString();
}
