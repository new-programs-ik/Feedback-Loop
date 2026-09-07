"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { fieldClasses } from "@/components/ui/select";

export type TypeaheadOption = { id: string; label: string; hint?: string };

/** A keyboard-first combobox over a small in-memory list (instructors, courses, staff): type to
 *  filter, ↑/↓ to move, Enter to pick, Esc to close. Fully controlled by `value`; typing clears
 *  the selection so the parent always knows whether an option or free text is in the box.
 *  `onCreate` (optional) adds a last row "Create “…”" for names that do not exist yet. */
export function Typeahead({
  id,
  options,
  value,
  onChange,
  onCreate,
  placeholder,
  ariaLabel,
  className,
  disabled,
  limit = 8,
}: {
  id?: string;
  options: TypeaheadOption[];
  value: TypeaheadOption | null;
  onChange: (next: TypeaheadOption | null) => void;
  onCreate?: (text: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
  disabled?: boolean;
  limit?: number;
}) {
  const reactId = React.useId();
  const inputId = id ?? `${reactId}-input`;
  const listId = `${reactId}-list`;
  const [query, setQuery] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(0);

  const text = value ? value.label : query;
  const q = query.trim().toLowerCase();
  const filtered = React.useMemo(() => {
    if (!q) return options.slice(0, limit);
    const starts = options.filter((o) => o.label.toLowerCase().startsWith(q));
    const contains = options.filter((o) => !o.label.toLowerCase().startsWith(q) && o.label.toLowerCase().includes(q));
    return [...starts, ...contains].slice(0, limit);
  }, [options, q, limit]);
  const canCreate = !!onCreate && q.length > 1 && !options.some((o) => o.label.toLowerCase() === q);
  const rowCount = filtered.length + (canCreate ? 1 : 0);

  const pick = (i: number) => {
    if (i < filtered.length) {
      onChange(filtered[i]);
      setQuery("");
    } else if (canCreate) {
      onCreate!(query.trim());
      setQuery("");
    }
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(rowCount - 1, a + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (e.key === "Enter") {
      if (open && rowCount > 0) {
        e.preventDefault();
        pick(Math.min(active, rowCount - 1));
      }
    } else if (e.key === "Escape") {
      if (open) {
        e.preventDefault();
        setOpen(false);
      }
    }
  };

  return (
    <div className={cn("relative", className)}>
      <input
        id={inputId}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && rowCount > 0 ? `${listId}-${Math.min(active, rowCount - 1)}` : undefined}
        aria-label={ariaLabel}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
        value={text}
        onChange={(e) => {
          if (value) onChange(null);
          setQuery(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        className={cn(fieldClasses, "placeholder:text-muted-foreground w-full px-3 py-1")}
      />
      {open && rowCount > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="bg-popover text-popover-foreground shadow-pop absolute z-30 mt-1 max-h-64 w-full min-w-48 overflow-auto rounded-md border p-1 text-sm"
        >
          {filtered.map((o, i) => (
            <li
              key={o.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setActive(i)}
              onClick={() => pick(i)}
              className={cn(
                "flex cursor-pointer items-center justify-between gap-3 rounded-sm px-2 py-1.5",
                i === active ? "bg-accent text-accent-foreground" : "",
              )}
            >
              <span className="truncate">{o.label}</span>
              {o.hint && <span className="text-muted-foreground shrink-0 text-[11px]">{o.hint}</span>}
            </li>
          ))}
          {canCreate && (
            <li
              id={`${listId}-${filtered.length}`}
              role="option"
              aria-selected={active === filtered.length}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setActive(filtered.length)}
              onClick={() => pick(filtered.length)}
              className={cn(
                "text-primary cursor-pointer rounded-sm px-2 py-1.5",
                active === filtered.length ? "bg-accent" : "",
              )}
            >
              Create “{query.trim()}”
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
