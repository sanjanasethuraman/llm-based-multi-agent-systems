import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_KEY = "visual-mas-theme";
const THEMES = new Set(["dark", "light"]);

function getStoredTheme() {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return THEMES.has(stored) ? stored : null;
  } catch {
    return null;
  }
}

function getSystemTheme() {
  if (typeof window === "undefined" || !window.matchMedia) {
    return "dark";
  }
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function getInitialTheme() {
  const stored = getStoredTheme();
  if (stored) {
    return stored;
  }
  return getSystemTheme();
}

export function useThemeMode() {
  const [theme, setThemeState] = useState(getInitialTheme);
  const userHasChosenTheme = useRef(Boolean(getStoredTheme()));

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
  }, [theme]);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia || userHasChosenTheme.current) {
      return undefined;
    }
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const handleChange = (event) => {
      if (!userHasChosenTheme.current) {
        setThemeState(event.matches ? "light" : "dark");
      }
    };
    media.addEventListener?.("change", handleChange);
    return () => media.removeEventListener?.("change", handleChange);
  }, []);

  const setTheme = useCallback((nextTheme) => {
    setThemeState((currentTheme) => {
      const resolvedTheme = typeof nextTheme === "function" ? nextTheme(currentTheme) : nextTheme;
      if (!THEMES.has(resolvedTheme)) {
        return currentTheme;
      }
      userHasChosenTheme.current = true;
      if (typeof window !== "undefined") {
        try {
          window.localStorage.setItem(STORAGE_KEY, resolvedTheme);
        } catch {
          // Theme switching should still work when storage is unavailable.
        }
      }
      return resolvedTheme;
    });
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  }, [setTheme]);

  return { theme, setTheme, toggleTheme };
}
