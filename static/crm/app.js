(() => {
  document.documentElement.classList.add("js-ready");
  const shell = document.querySelector(".app-shell");
  const sidebar = document.querySelector(".sidebar");
  const collapse = document.querySelector(".sidebar-collapse");
  const open = document.querySelector(".mobile-menu");
  const close = document.querySelector(".sidebar-close");
  const backdrop = document.querySelector(".sidebar-backdrop");
  const mobile = matchMedia("(max-width: 760px)");

  function setMobileOpen(value) {
    sidebar.classList.toggle("is-mobile-open", value);
    open.setAttribute("aria-expanded", String(value));
    sidebar.inert = mobile.matches && !value;
    backdrop.hidden = !value;
    document.body.style.overflow = value ? "hidden" : "";
    if (!value && sidebar.contains(document.activeElement)) open.focus();
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
    if (event.key === "Escape" && sidebar.classList.contains("is-mobile-open"))
      setMobileOpen(false);
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
