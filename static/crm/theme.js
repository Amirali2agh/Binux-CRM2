(() => {
  const storageKey = "binux-crm-theme";
  let theme = "light";

  try {
    const savedTheme = window.localStorage.getItem(storageKey);
    if (savedTheme === "light" || savedTheme === "dark") theme = savedTheme;
  } catch (_) {
    // Keep the light theme when browser storage is unavailable.
  }

  document.documentElement.dataset.theme = theme;
})();
