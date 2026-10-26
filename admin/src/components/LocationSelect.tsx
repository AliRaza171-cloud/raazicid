import { useEffect, useState } from "react";
import { api, type LocationItem } from "../lib/api";

const LABELS = ["Province", "City", "Region", "Area"];

type Level = { options: LocationItem[]; selected: string };

/** Province > City > Region > Area dropdowns. Reports the most specific place chosen (or null). */
export default function LocationSelect({
  onChange,
  compact = false,
  allLabel = "All",
}: {
  onChange: (id: string | null, path: string[], chosen: LocationItem[]) => void;
  compact?: boolean;
  allLabel?: string;
}) {
  const [levels, setLevels] = useState<Level[]>([]);

  useEffect(() => {
    api<LocationItem[]>("/locations").then((options) => setLevels([{ options, selected: "" }])).catch(() => undefined);
  }, []);

  const choose = async (index: number, id: string) => {
    const next = levels.slice(0, index + 1).map((l, i) => (i === index ? { ...l, selected: id } : l));
    const chosen = next.map((l) => l.options.find((o) => o.id === l.selected)).filter(Boolean) as LocationItem[];
    onChange(chosen.length ? chosen[chosen.length - 1].id : null, chosen.map((c) => c.name), chosen);
    if (id && index < 3) {
      const children = await api<LocationItem[]>(`/locations?parent_id=${id}`).catch(() => []);
      if (children.length) next.push({ options: children, selected: "" });
    }
    setLevels(next);
  };

  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {levels.map((l, i) => (
        <div key={i} style={{ display: "flex", flexDirection: "column", gap: 4, flex: compact ? undefined : "1 1 140px" }}>
          {!compact && <label style={{ margin: 0 }}>{LABELS[i]}</label>}
          <select className="select" aria-label={LABELS[i]} value={l.selected} onChange={(e) => choose(i, e.target.value)}>
            <option value="">{i === 0 ? `${allLabel} provinces` : `${allLabel} in ${levels[i - 1].options.find((o) => o.id === levels[i - 1].selected)?.name ?? ""}`}</option>
            {l.options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </div>
      ))}
    </div>
  );
}
