// Light by default; dark only when the user picks it. The choice is stamped on <html data-theme>
// (index.html does it before first paint, so there's no flash) and remembered per browser.

export type Theme = "light" | "dark";
const KEY = "uta-theme";

function saved(): Theme {
  try {
    return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

class ThemeStore {
  current = $state<Theme>(saved());

  toggle() {
    this.current = this.current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = this.current;
    try {
      localStorage.setItem(KEY, this.current);
    } catch {
      // storage blocked: the choice lasts for this page only
    }
  }
}

export const theme = new ThemeStore();
