import { useEffect, useState } from "react";
import { api } from "../api/client";
import { SymbolSearchResult } from "../types";
import { Icon } from "./Icon";

interface Props {
  query: string;
  onQueryChange: (query: string) => void;
  isCustom: boolean;
  onCustomChange: (isCustom: boolean) => void;
  selectedName?: string;
  selected: boolean;
  onSelect: (symbol: SymbolSearchResult) => void;
}

// Isolated so a future "save chosen candidate" endpoint only changes onSelect wiring.
export function SymbolPicker({ query, onQueryChange, isCustom, onCustomChange, selectedName, selected, onSelect }: Props) {
  const [results, setResults] = useState<SymbolSearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (isCustom || selected || query.trim().length < 2) {
      setResults([]);
      return;
    }
    const timeout = window.setTimeout(() => {
      setSearching(true);
      api
        .get<SymbolSearchResult[]>("/symbols/search", { params: { q: query.trim() } })
        .then((response) => setResults(response.data))
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [query, isCustom, selected]);

  return (
    <div className="symbol">
      <label className="combo" htmlFor="tx-symbol">
        <Icon name="search" size={16} />
        <input
          id="tx-symbol"
          role="combobox"
          aria-expanded={results.length > 0}
          aria-controls="tx-symbol-results"
          autoComplete="off"
          required
          placeholder="Type a symbol or name"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
        />
        {searching && <span className="muted">Searching…</span>}
        {selected && !isCustom && <span className="chip chip-pos"><span className="d" />Matched</span>}
      </label>
      {results.length > 0 && (
        <div className="symbol-results" id="tx-symbol-results" role="listbox">
          {results.map((symbol) => (
            <button className="symbol-result" type="button" role="option" aria-selected="false" key={`${symbol.id}-${symbol.provider_symbol}`} onClick={() => onSelect(symbol)}>
              <span className="tk">{symbol.symbol.slice(0, 4)}</span>
              <span className="symbol-text">
                <b className="mono">{symbol.provider_symbol}</b>
                <span className="muted">{[symbol.name, symbol.exchange, symbol.currency, symbol.asset_type].filter(Boolean).join(" · ")}</span>
              </span>
            </button>
          ))}
        </div>
      )}
      {selected && !isCustom && selectedName && <p className="hint">{selectedName}</p>}
      <label className="check">
        <input className="cb" type="checkbox" checked={isCustom} onChange={(event) => onCustomChange(event.target.checked)} />
        Not listed? Use a custom symbol (no live price)
      </label>
    </div>
  );
}
