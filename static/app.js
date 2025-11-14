(() => {
  const svgNS = "http://www.w3.org/2000/svg";
  const dataEl = document.getElementById("bootstrap-data");
  const spriteUrl = document.body.dataset.spriteUrl || "/svgs.html";
  const categoriesEl = document.querySelector("[data-role='categories']");
  const statusEl = document.querySelector("[data-role='status']");
  const disableOutput = document.getElementById("disable-output");
  const markdownOutput = document.getElementById("markdown-output");

  let state = dataEl ? JSON.parse(dataEl.textContent) : null;

  const showStatus = (message, success = true) => {
    if (!statusEl) {
      return;
    }
    statusEl.textContent = message;
    statusEl.dataset.visible = "true";
    statusEl.style.background = success ? "rgba(12,30,60,0.95)" : "rgba(199,44,65,0.95)";
    window.clearTimeout(showStatus._timer);
    showStatus._timer = window.setTimeout(() => {
      statusEl.dataset.visible = "false";
    }, 2800);
  };

  const renderOutputs = (payload) => {
    if (!payload) {
      return;
    }
    disableOutput.value = payload.disableArgument || "";
    markdownOutput.value = payload.markdown || "";
  };

  const createIcon = (code) => {
    const svg = document.createElementNS(svgNS, "svg");
    const use = document.createElementNS(svgNS, "use");
    use.setAttribute("href", `${spriteUrl}#${code}`);
    use.setAttributeNS(
      "http://www.w3.org/1999/xlink",
      "xlink:href",
      `${spriteUrl}#${code}`
    );
    svg.appendChild(use);
    return svg;
  };

  const renderCategories = (payload) => {
    if (!categoriesEl || !payload) {
      return;
    }
    categoriesEl.innerHTML = "";
    payload.categories.forEach((category) => {
      const section = document.createElement("article");
      section.className = "dlc-section";

      const heading = document.createElement("h2");
      heading.textContent = category.title;
      section.appendChild(heading);

      const grid = document.createElement("div");
      grid.className = "dlc-grid";
      category.items.forEach((item) => {
        const card = document.createElement("div");
        card.className = "dlc-card";
        card.dataset.enabled = item.enabled ? "true" : "false";

        const icon = createIcon(item.code);
        card.appendChild(icon);

        const name = document.createElement("div");
        name.className = "dlc-name";
        name.textContent = item.name;
        card.appendChild(name);

        const code = document.createElement("div");
        code.className = "dlc-code";
        code.textContent = item.code;
        card.appendChild(code);

        const toggle = document.createElement("button");
        toggle.className = "toggle";
        toggle.type = "button";
        toggle.dataset.code = item.code;
        toggle.dataset.enabled = item.enabled ? "true" : "false";
        toggle.textContent = item.enabled ? "Enabled" : "Disabled";
        card.appendChild(toggle);

        grid.appendChild(card);
      });

      section.appendChild(grid);
      categoriesEl.appendChild(section);
    });
  };

  const render = (payload) => {
    state = payload;
    renderCategories(payload);
    renderOutputs(payload);
  };

  const request = async (url, options = {}) => {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = data.error || "Request failed.";
      throw new Error(message);
    }
    return data;
  };

  const handleToggle = async (button) => {
    const code = button.dataset.code;
    const nextEnabled = button.dataset.enabled !== "true";
    showStatus("Saving...");
    try {
      const payload = await request("/api/toggle", {
        method: "POST",
        body: JSON.stringify({ code, enabled: nextEnabled }),
      });
      render(payload);
      showStatus("State updated.");
    } catch (error) {
      showStatus(error.message, false);
    }
  };

  const handleReset = async () => {
    if (!window.confirm("Reset all DLC toggles to the default checklist?")) {
      return;
    }
    showStatus("Resetting...");
    try {
      const payload = await request("/api/reset", { method: "POST" });
      render(payload);
      showStatus("Defaults restored.");
    } catch (error) {
      showStatus(error.message, false);
    }
  };

  const handleRefresh = async () => {
    showStatus("Refreshing...");
    try {
      const payload = await request("/api/state");
      render(payload);
      showStatus("Latest data loaded.");
    } catch (error) {
      showStatus(error.message, false);
    }
  };

  const handleDisableArgumentUpdate = async () => {
    if (!disableOutput) {
      return;
    }
    const argument = disableOutput.value.trim();
    if (!argument) {
      showStatus("Enter a -disablepacks argument first.", false);
      return;
    }
    showStatus("Updating disable list...");
    try {
      const payload = await request("/api/disable", {
        method: "POST",
        body: JSON.stringify({ argument }),
      });
      render(payload);
      showStatus("Disable list applied.");
    } catch (error) {
      showStatus(error.message, false);
    }
  };

  const handleCopy = async (targetId) => {
    const field = document.getElementById(targetId);
    if (!field) {
      return;
    }
    try {
      await navigator.clipboard.writeText(field.value);
      showStatus("Copied to clipboard.");
    } catch {
      field.select();
      document.execCommand("copy");
      showStatus("Copied to clipboard.");
    }
  };

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    if (target.matches(".toggle")) {
      handleToggle(target);
    } else if (target.dataset.action === "reset") {
      handleReset();
    } else if (target.dataset.action === "refresh") {
      handleRefresh();
    } else if (target.dataset.action === "apply-disable") {
      handleDisableArgumentUpdate();
    } else if (target.dataset.copyTarget) {
      handleCopy(target.dataset.copyTarget);
    }
  });

  if (state) {
    render(state);
  } else {
    handleRefresh();
  }
})();
