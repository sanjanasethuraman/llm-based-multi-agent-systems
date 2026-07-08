import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "visual-mas-theme";
const THEMES = new Set(["dark", "light"]);

function getSystemTheme() {
  if (typeof window === "undefined" || !window.matchMedia) {
    return "dark";
  }
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function getInitialTheme() {
  if (typeof window === "undefined") {
    return "dark";
  }
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (THEMES.has(stored)) {
    return stored;
  }
  return getSystemTheme();
}

export function useThemeMode() {
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia || window.localStorage.getItem(STORAGE_KEY)) {
      return undefined;
    }
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const handleChange = (event) => setTheme(event.matches ? "light" : "dark");
    media.addEventListener?.("change", handleChange);
    return () => media.removeEventListener?.("change", handleChange);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  }, []);

  return { theme, setTheme, toggleTheme };
}
