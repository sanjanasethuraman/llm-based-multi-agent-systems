import { Check, ChevronDown, Loader2, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

const DEFAULT_LIMIT = 20;

export default function DiseaseCombobox({
  value,
  onChange,
  label = "Disease",
  placeholder = "Search diseases in PrimeKG",
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [available, setAvailable] = useState(true);
  const [message, setMessage] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);
  const wrapperRef = useRef(null);
  const query = String(value || "");

  useEffect(() => {
    const handlePointerDown = (event) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  useEffect(() => {
    if (!open) {
      setLoading(false);
      return undefined;
    }
    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ query, limit: String(DEFAULT_LIMIT) });
        const response = await fetch(`/api/primekg/diseases?${params.toString()}`, { signal: controller.signal });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "Disease suggestions failed.");
        }
        setAvailable(Boolean(data.available));
        setMessage(data.message || "");
        setSuggestions(Array.isArray(data.diseases) ? data.diseases : []);
        setActiveIndex(-1);
      } catch (error) {
        if (error.name !== "AbortError") {
          setAvailable(false);
          setMessage(error.message || "Disease suggestions unavailable.");
          setSuggestions([]);
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }, 240);

    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [open, query]);

  const hasExact = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return suggestions.some((item) => item.name?.trim().toLowerCase() === normalized || item.id?.trim().toLowerCase() === normalized);
  }, [query, suggestions]);

  const selectDisease = (disease) => {
    onChange(disease?.name || disease?.id || query);
    setOpen(false);
  };

  const useTypedValue = () => {
    onChange(query);
    setOpen(false);
  };

  const moveActive = (direction) => {
    if (!open) {
      setOpen(true);
      return;
    }
    const max = suggestions.length - 1;
    if (max < 0) return;
    setActiveIndex((current) => {
      if (direction > 0) return current >= max ? 0 : current + 1;
      return current <= 0 ? max : current - 1;
    });
  };

  return (
    <label className="disease-combobox" ref={wrapperRef}>
      <span>{label}</span>
      <div className={`disease-combobox-control ${open ? "open" : ""}`}>
        <Search size={15} />
        <input
          value={query}
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              moveActive(1);
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              moveActive(-1);
            } else if (event.key === "Enter") {
              if (open && activeIndex >= 0 && suggestions[activeIndex]) {
                event.preventDefault();
                selectDisease(suggestions[activeIndex]);
              }
            } else if (event.key === "Escape") {
              setOpen(false);
            }
          }}
          placeholder={placeholder}
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          aria-label="Search PrimeKG diseases"
        />
        {loading ? <Loader2 className="spin" size={15} /> : null}
        {query ? (
          <button type="button" onClick={() => onChange("")} aria-label="Clear disease search">
            <X size={14} />
          </button>
        ) : (
          <ChevronDown size={15} />
        )}
      </div>

      {open ? (
        <div className="disease-combobox-menu" role="listbox">
          {!available ? (
            <div className="disease-combobox-state warning">
              PrimeKG kg.csv not found. Download/place it in data/primekg/kg.csv.
            </div>
          ) : loading ? (
            <div className="disease-combobox-state">Loading disease suggestions...</div>
          ) : suggestions.length ? (
            suggestions.map((disease, index) => (
              <button
                key={disease.id || `${disease.name}-${index}`}
                type="button"
                role="option"
                aria-selected={index === activeIndex}
                className={index === activeIndex ? "active" : ""}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => selectDisease(disease)}
              >
                <div>
                  <strong>{disease.name || disease.id}</strong>
                  <span>{[disease.source, disease.id].filter(Boolean).join(" - ")}</span>
                </div>
                <em>{disease.match || "match"}</em>
                {hasExact && index === 0 ? <Check size={14} /> : null}
              </button>
            ))
          ) : (
            <div className="disease-combobox-state">No matching diseases found</div>
          )}

          {query.trim() ? (
            <button type="button" className="disease-use-typed" onClick={useTypedValue}>
              Use typed value anyway: <strong>{query}</strong>
            </button>
          ) : null}

          {message && available ? <div className="disease-combobox-hint">{message}</div> : null}
        </div>
      ) : null}
    </label>
  );
}
