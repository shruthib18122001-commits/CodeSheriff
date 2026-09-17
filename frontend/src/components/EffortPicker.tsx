import { useEffect, useRef, useState } from "react";
import type { ThinkingLevel } from "../lib/api";

interface Option {
  value: ThinkingLevel;
  label: string;
  description: string;
}

const OPTIONS: Option[] = [
  { value: "low", label: "Low", description: "Light reasoning for quick, straightforward questions" },
  { value: "medium", label: "Medium", description: "Balanced reasoning for typical questions" },
  { value: "high", label: "High", description: "Deep reasoning for complex, multi-step questions" },
];

interface Props {
  value: ThinkingLevel;
  onChange: (value: ThinkingLevel) => void;
  disabled?: boolean;
}

/** Compact "effort" picker: a pill trigger that opens a menu of reasoning levels. */
function EffortPicker({ value, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const current = OPTIONS.find((o) => o.value === value) ?? OPTIONS[0];

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  return (
    <div className="effort-picker" ref={rootRef}>
      <button
        type="button"
        className="effort-picker-trigger"
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
      >
        Effort: {current.label}
      </button>

      {open && (
        <div className="effort-picker-menu">
          {OPTIONS.map((opt) => (
            <div
              key={opt.value}
              className="effort-picker-option"
              onClick={() => {
                onChange(opt.value);
                setOpen(false);
              }}
            >
              <div>
                <div className="effort-picker-option-label">{opt.label}</div>
                <div className="effort-picker-option-desc">{opt.description}</div>
              </div>
              {opt.value === value && <span className="effort-picker-check">✓</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default EffortPicker;
