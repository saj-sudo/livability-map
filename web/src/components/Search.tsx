"use client";

// Place search (SPEC §10): an accessible combobox over the bundled gazetteer. The JSON is
// fetched from the same origin the first time the box is focused and kept in module scope;
// nothing is sent anywhere (invariant 7). Picking a result flies the map there.

import { useEffect, useId, useRef, useState } from "react";
import { GAZETTEER_URL } from "../lib/config";
import { countryName } from "../lib/inspect";
import { parseGazetteer, rankPlaces, type GazetteerFile, type Place } from "../lib/search";

let gazetteer: Promise<Place[]> | null = null;
function loadGazetteer(): Promise<Place[]> {
  if (!gazetteer) {
    gazetteer = fetch(GAZETTEER_URL)
      .then((r) => {
        if (!r.ok) throw new Error(`gazetteer ${r.status}`);
        return r.json() as Promise<GazetteerFile>;
      })
      .then(parseGazetteer)
      .catch((err) => {
        gazetteer = null; // try again on the next focus
        throw err;
      });
  }
  return gazetteer;
}

interface Props {
  onPick: (place: Place) => void;
  /** e.g. "second place" while comparing; changes the placeholder */
  placeholder?: string;
  autoFocus?: boolean;
  className?: string;
}

export default function Search({ onPick, placeholder = "Search a city or region", autoFocus, className = "" }: Props) {
  const [query, setQuery] = useState("");
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "failed">("idle");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const root = useRef<HTMLDivElement>(null);

  const ensureLoaded = () => {
    if (places || status === "loading") return;
    setStatus("loading");
    loadGazetteer()
      .then((p) => {
        setPlaces(p);
        setStatus("idle");
      })
      .catch(() => setStatus("failed"));
  };

  const results = places ? rankPlaces(query, places) : [];
  const showList = open && query.trim().length > 0;

  // close when focus leaves the combobox
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);

  const pick = (p: Place) => {
    onPick(p);
    setQuery(p.name);
    setOpen(false);
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(results.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      if (showList && results[active]) {
        e.preventDefault();
        pick(results[active]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      if (!showList) setQuery("");
    }
  };

  return (
    <div ref={root} className={`relative ${className}`}>
      <div className="relative">
        <svg className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-muted" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <circle cx="7" cy="7" r="4.5" />
          <path d="M10.5 10.5L14 14" />
        </svg>
        <input
          type="search"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showList && results[active] ? `${listId}-${active}` : undefined}
          aria-label="Search a city or region"
          placeholder={placeholder}
          autoFocus={autoFocus}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
            setOpen(true);
          }}
          onFocus={() => {
            ensureLoaded();
            setOpen(true);
          }}
          onKeyDown={onKey}
          className="h-8 w-full rounded-panel border border-rule bg-panel-solid pl-7 pr-2 text-[13px] text-ink placeholder:text-muted focus:border-accent focus:outline-none"
        />
      </div>
      {showList && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 overflow-hidden rounded-panel border border-rule bg-panel-solid shadow-[0_8px_24px_-12px_rgba(0,0,0,.35)]">
          {status === "failed" && <p className="px-3 py-2 text-[12px] text-muted">The place list could not be loaded. Check the connection and try again.</p>}
          {status === "loading" && <p className="px-3 py-2 text-[12px] text-muted">Loading place names…</p>}
          {status === "idle" && places && results.length === 0 && <p className="px-3 py-2 text-[12px] text-muted">No city or region matches &ldquo;{query.trim()}&rdquo;. Try another spelling or a larger place nearby.</p>}
          {results.length > 0 && (
            <ul id={listId} role="listbox" aria-label="Places" className="max-h-80 overflow-auto py-1">
              {results.map((p, i) => (
                <li
                  key={`${p.kind}-${p.iso2}-${p.name}-${p.lat}`}
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === active}
                  onPointerDown={(e) => e.preventDefault()}
                  onClick={() => pick(p)}
                  onMouseEnter={() => setActive(i)}
                  className={`flex cursor-pointer items-baseline justify-between gap-3 px-3 py-1.5 text-[13px] ${i === active ? "bg-rule/70" : ""}`}
                >
                  <span className="truncate">{p.name}</span>
                  <span className="shrink-0 text-[12px] text-muted">
                    {p.kind === "city" ? "City" : "Region"} in {countryName(p.iso2 || null)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="border-t border-rule px-3 py-1 text-[11px] text-muted">Names from Natural Earth and geoBoundaries; nothing leaves this page.</p>
        </div>
      )}
    </div>
  );
}
