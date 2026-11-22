(() => {
  document.documentElement.classList.add("js-ready");
  const shell = document.querySelector(".app-shell");
  const sidebar = document.querySelector(".sidebar");
  const collapse = document.querySelector(".sidebar-collapse");
  const open = document.querySelector(".mobile-menu");
  const close = document.querySelector(".sidebar-close");
  const backdrop = document.querySelector(".sidebar-backdrop");
  const workspace = document.querySelector(".workspace");
  const mobile = matchMedia("(max-width: 760px)");

  function setMobileOpen(value) {
    const restoreFocus = sidebar.contains(document.activeElement);
    sidebar.classList.toggle("is-mobile-open", value);
    open.setAttribute("aria-expanded", String(value));
    sidebar.inert = mobile.matches && !value;
    workspace.inert = mobile.matches && value;
    backdrop.hidden = !value;
    document.body.style.overflow = value ? "hidden" : "";
    if (value) close.focus();
    else if (mobile.matches && restoreFocus) open.focus();
    else if (!mobile.matches && restoreFocus) collapse.focus();
  }

  function setCollapsed(value) {
    shell.classList.toggle("sidebar-collapsed", value);
    collapse.setAttribute("aria-expanded", String(!value));
    collapse.setAttribute(
      "aria-label",
      value ? "بازکردن سایدبار" : "جمع‌کردن سایدبار",
    );
    collapse.title = value ? "بازکردن سایدبار" : "جمع‌کردن سایدبار";
    if (value)
      document
        .querySelectorAll(".group-toggle")
        .forEach((button) => setGroup(button, false));
  }

  function setGroup(button, expanded) {
    button.setAttribute("aria-expanded", String(expanded));
    document.getElementById(button.getAttribute("aria-controls")).hidden =
      !expanded;
  }

  document.querySelectorAll(".nav-group").forEach((group) => {
    const button = group.querySelector(".group-toggle");
    setGroup(button, group.dataset.active === "true");
    button.addEventListener("click", () => {
      if (shell.classList.contains("sidebar-collapsed")) {
        setCollapsed(false);
        setGroup(button, true);
      } else {
        setGroup(button, button.getAttribute("aria-expanded") !== "true");
      }
    });
  });

  collapse.addEventListener("click", () =>
    setCollapsed(!shell.classList.contains("sidebar-collapsed")),
  );
  open.addEventListener("click", () => setMobileOpen(true));
  close.addEventListener("click", () => setMobileOpen(false));
  backdrop.addEventListener("click", () => setMobileOpen(false));
  document.addEventListener("keydown", (event) => {
    if (!sidebar.classList.contains("is-mobile-open")) return;
    if (event.key === "Escape") {
      setMobileOpen(false);
    } else if (event.key === "Tab") {
      const focusable = [...sidebar.querySelectorAll("a[href], button")].filter(
        (element) => !element.closest("[hidden]") && element.getClientRects().length,
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });
  sidebar.querySelectorAll(".submenu a").forEach((link) => {
    link.addEventListener("click", () => {
      if (mobile.matches) setMobileOpen(false);
    });
  });
  mobile.addEventListener("change", () => {
    if (mobile.matches) setCollapsed(false);
    setMobileOpen(false);
  });
  setMobileOpen(false);
})();
