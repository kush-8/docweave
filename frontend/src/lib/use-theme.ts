import { useEffect, useState } from "react";

type Theme = "light" | "dark";

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === "dark" ? "dark" : "light",
  );
  const [preference, setPreference] = useState<Theme | null>(() => {
    try {
      const stored = localStorage.getItem("docweave-theme");
      return stored === "light" || stored === "dark" ? stored : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const followDevice = () => {
      if (!preference) setTheme(media.matches ? "dark" : "light");
    };
    followDevice();
    media.addEventListener("change", followDevice);
    return () => media.removeEventListener("change", followDevice);
  }, [preference]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.style.colorScheme = theme;
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", theme === "dark" ? "#19263A" : "#EAF0F8");
  }, [theme]);

  function chooseTheme(next: Theme | null) {
    setPreference(next);
    setTheme(
      next ??
        (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
    );
    try {
      if (next) localStorage.setItem("docweave-theme", next);
      else localStorage.removeItem("docweave-theme");
    } catch {
      /* Theme still works for this visit when storage is unavailable. */
    }
  }

  return { theme, preference, chooseTheme };
}
