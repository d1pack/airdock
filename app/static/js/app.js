document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    window.lucide.createIcons();
  }

  const sidebarCollapse = document.querySelector(".sidebar__collapse");
  if (sidebarCollapse) {
    const storageKey = "airdock.sidebarCollapsed";
    const setSidebarCollapsed = (collapsed) => {
      document.body.classList.toggle("sidebar-collapsed", collapsed);
      sidebarCollapse.setAttribute("aria-expanded", collapsed ? "false" : "true");
      sidebarCollapse.setAttribute("aria-label", collapsed ? "Развернуть меню" : "Свернуть меню");
      try {
        window.localStorage.setItem(storageKey, collapsed ? "1" : "0");
      } catch (error) {
        // Ignore private-mode storage failures.
      }
    };

    let shouldCollapse = false;
    try {
      shouldCollapse = window.localStorage.getItem(storageKey) === "1";
    } catch (error) {
      shouldCollapse = false;
    }
    setSidebarCollapsed(shouldCollapse);
    sidebarCollapse.addEventListener("click", () => {
      setSidebarCollapsed(!document.body.classList.contains("sidebar-collapsed"));
    });
  }

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  document.querySelectorAll("[data-char-source]").forEach((field) => {
    const counter = document.querySelector(`[data-char-count="${field.getAttribute("data-char-source")}"]`);
    if (!counter) {
      return;
    }
    const limit = Number(field.getAttribute("maxlength")) || 0;
    const updateCounter = () => {
      counter.textContent = `${field.value.length} / ${limit}`;
    };
    updateCounter();
    field.addEventListener("input", updateCounter);
  });

  const toastViewport = document.querySelector("[data-toast-viewport]");
  const shownToasts = new Map();

  const showToast = ({ title, message, href, action = "Открыть инструкцию", variant = "error" }) => {
    if (!toastViewport) {
      return;
    }

    const key = `${variant}:${title}:${message}`;
    const now = Date.now();
    if (shownToasts.has(key) && now - shownToasts.get(key) < 60000) {
      return;
    }
    shownToasts.set(key, now);

    const toast = document.createElement("section");
    toast.className = `toast toast--${variant}`;
    toast.innerHTML = `
      <div class="toast__icon">
        <i data-lucide="${variant === "error" ? "triangle-alert" : "info"}" aria-hidden="true"></i>
      </div>
      <div class="toast__body">
        <strong>${escapeHtml(title)}</strong>
        <p>${escapeHtml(message)}</p>
        ${href ? `<a href="${escapeHtml(href)}">${escapeHtml(action)}</a>` : ""}
      </div>
      <button class="toast__close" type="button" aria-label="Закрыть">
        <i data-lucide="x" aria-hidden="true"></i>
      </button>
    `;
    toastViewport.appendChild(toast);
    if (window.lucide) {
      window.lucide.createIcons({ nodes: toast.querySelectorAll("[data-lucide]") });
    }

    const close = () => {
      toast.classList.add("toast--closing");
      window.setTimeout(() => toast.remove(), 240);
    };
    toast.querySelector(".toast__close")?.addEventListener("click", close);
    window.setTimeout(close, 11000);
  };

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const message = form.getAttribute("data-confirm");
      if (message && !window.confirm(message)) {
        event.preventDefault();
      }
    });
  });

  document.querySelectorAll("[data-open-dialog]").forEach((button) => {
    button.addEventListener("click", () => {
      const dialog = document.getElementById(button.getAttribute("data-open-dialog"));
      if (dialog && typeof dialog.showModal === "function") {
        dialog.showModal();
      }
    });
  });

  document.querySelectorAll("dialog [data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => {
      button.closest("dialog")?.close();
    });
  });

  document.querySelectorAll("dialog.modal").forEach((dialog) => {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        dialog.close();
      }
    });
  });

  const closeCustomSelects = (except = null) => {
    document.querySelectorAll(".custom-select.is-open").forEach((customSelect) => {
      if (customSelect !== except) {
        customSelect.classList.remove("is-open");
        customSelect.closest(".panel, .form-panel, label")?.classList.remove("select-layer-open");
        customSelect.querySelector(".custom-select__button")?.setAttribute("aria-expanded", "false");
      }
    });
  };

  const enhanceSelects = () => {
    document.querySelectorAll("select:not([data-native-select]):not([data-custom-select-ready])").forEach((select) => {
      select.dataset.customSelectReady = "true";
      const wrapper = document.createElement("div");
      wrapper.className = "custom-select";
      if (select.disabled) {
        wrapper.classList.add("is-disabled");
      }

      const button = document.createElement("button");
      button.className = "custom-select__button";
      button.type = "button";
      button.setAttribute("aria-haspopup", "listbox");
      button.setAttribute("aria-expanded", "false");

      const value = document.createElement("span");
      value.className = "custom-select__value";
      const icon = document.createElement("i");
      icon.setAttribute("data-lucide", "chevron-down");
      icon.setAttribute("aria-hidden", "true");
      button.append(value, icon);

      const menu = document.createElement("div");
      menu.className = "custom-select__menu";
      menu.setAttribute("role", "listbox");

      const syncValue = () => {
        const selected = select.selectedOptions[0] || select.options[0];
        const selectedText = selected?.textContent?.trim() || "";
        value.textContent = selectedText;
        value.title = selectedText;
        button.title = selectedText;
        menu.querySelectorAll(".custom-select__option").forEach((customOption, index) => {
          const nativeOption = select.options[index];
          const isSelected = customOption.dataset.value === select.value;
          customOption.classList.toggle("is-selected", isSelected);
          customOption.setAttribute("aria-selected", isSelected ? "true" : "false");
          customOption.hidden = Boolean(nativeOption?.hidden);
          customOption.disabled = Boolean(nativeOption?.disabled);
        });
      };

      Array.from(select.options).forEach((option) => {
        const item = document.createElement("button");
        item.className = "custom-select__option";
        item.type = "button";
        item.role = "option";
        item.dataset.value = option.value;
        item.textContent = option.textContent;
        item.title = option.textContent.trim();
        item.disabled = option.disabled;
        item.addEventListener("click", () => {
          if (option.disabled) {
            return;
          }
          select.value = option.value;
          select.dispatchEvent(new Event("change", { bubbles: true }));
          syncValue();
          closeCustomSelects();
        });
        menu.append(item);
      });

      select.classList.add("native-select-hidden");
      select.parentNode.insertBefore(wrapper, select.nextSibling);
      wrapper.append(select, button, menu);
      syncValue();

      button.addEventListener("click", () => {
        if (select.disabled) {
          return;
        }
        const willOpen = !wrapper.classList.contains("is-open");
        closeCustomSelects(wrapper);
        wrapper.classList.toggle("is-open", willOpen);
        wrapper.closest(".panel, .form-panel, label")?.classList.toggle("select-layer-open", willOpen);
        button.setAttribute("aria-expanded", willOpen ? "true" : "false");
      });
      select.addEventListener("change", syncValue);
    });

    if (window.lucide) {
      window.lucide.createIcons({ nodes: document.querySelectorAll(".custom-select [data-lucide]") });
    }
  };

  enhanceSelects();
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".custom-select")) {
      closeCustomSelects();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeCustomSelects();
    }
  });

  const taskCreatePanel = document.querySelector("[data-task-create-panel]");
  const taskCreateToggle = document.querySelector("[data-task-create-toggle]");
  const taskCreateCloseButtons = document.querySelectorAll("[data-task-create-close]");
  if (taskCreatePanel && taskCreateToggle) {
    const setTaskCreateOpen = (open) => {
      taskCreatePanel.hidden = !open;
      taskCreatePanel.classList.toggle("is-collapsed", !open);
      taskCreatePanel.classList.toggle("is-open", open);
      taskCreateToggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        window.requestAnimationFrame(() => {
          taskCreatePanel.querySelector("input, .custom-select__button, select, textarea")?.focus();
        });
      } else {
        taskCreateToggle.focus();
      }
    };

    taskCreateToggle.addEventListener("click", () => {
      setTaskCreateOpen(taskCreatePanel.hidden);
    });
    taskCreateCloseButtons.forEach((button) => {
      button.addEventListener("click", () => setTaskCreateOpen(false));
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !taskCreatePanel.hidden) {
        setTaskCreateOpen(false);
      }
    });
  }

  const initPipelineBuilder = () => {
    const builder = document.querySelector("[data-pipeline-builder]");
    if (!builder) {
      return;
    }
    const projectCheckboxes = Array.from(builder.querySelectorAll("[data-pipeline-project-checkbox]"));
    const list = builder.querySelector("[data-pipeline-step-list]");
    if (!projectCheckboxes.length || !list) {
      return;
    }

    const refreshIndexes = () => {
      list.querySelectorAll("[data-pipeline-step]").forEach((step, index) => {
        const indexNode = step.querySelector(".pipeline-step-card__index");
        if (indexNode) {
          indexNode.textContent = String(index + 1);
        }
      });
    };

    const selectFirstVisibleOption = (select) => {
      const visibleOption = Array.from(select.options).find((option) => !option.hidden && !option.disabled);
      if (visibleOption && select.selectedOptions[0]?.hidden) {
        select.value = visibleOption.value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
    };

    const filterPlaybooks = () => {
      const projectIds = new Set(projectCheckboxes.filter((checkbox) => checkbox.checked).map((checkbox) => checkbox.value));
      list.querySelectorAll("[data-pipeline-playbook-select]").forEach((select) => {
        Array.from(select.options).forEach((option) => {
          const belongs = projectIds.has(option.getAttribute("data-project-id"));
          option.hidden = !belongs;
          option.disabled = !belongs;
        });
        selectFirstVisibleOption(select);
        select.dispatchEvent(new Event("change", { bubbles: true }));
      });
    };

    const stepTemplate = () => {
      const firstStep = list.querySelector("[data-pipeline-step]");
      const step = firstStep ? firstStep.cloneNode(true) : null;
      if (!step) {
        return null;
      }
      step.classList.remove("is-dragging");
      step.querySelectorAll(".custom-select").forEach((customSelect) => {
        const select = customSelect.querySelector("select");
        if (select) {
          select.classList.remove("native-select-hidden");
          select.removeAttribute("data-custom-select-ready");
          customSelect.replaceWith(select);
        }
      });
      return step;
    };

    const addStep = () => {
      const ghost = list.querySelector("[data-pipeline-add-step].pipeline-step-card--ghost");
      const step = stepTemplate();
      if (!step || !ghost) {
        return;
      }
      list.insertBefore(step, ghost);
      refreshIndexes();
      filterPlaybooks();
      enhanceSelects();
      if (window.lucide) {
        window.lucide.createIcons({ nodes: step.querySelectorAll("[data-lucide]") });
      }
    };

    list.addEventListener("click", (event) => {
      if (event.target.closest("[data-pipeline-add-step]")) {
        addStep();
        return;
      }
      const removeButton = event.target.closest("[data-pipeline-remove-step]");
      if (removeButton) {
        const steps = list.querySelectorAll("[data-pipeline-step]");
        if (steps.length > 1) {
          removeButton.closest("[data-pipeline-step]")?.remove();
          refreshIndexes();
        }
      }
    });

    let draggedStep = null;
    list.addEventListener("dragstart", (event) => {
      const step = event.target.closest("[data-pipeline-step]");
      if (!step) {
        return;
      }
      draggedStep = step;
      step.classList.add("is-dragging");
      event.dataTransfer.effectAllowed = "move";
    });
    list.addEventListener("dragend", () => {
      draggedStep?.classList.remove("is-dragging");
      draggedStep = null;
      refreshIndexes();
    });
    list.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (!draggedStep) {
        return;
      }
      const target = event.target.closest("[data-pipeline-step]");
      if (!target || target === draggedStep) {
        return;
      }
      const bounds = target.getBoundingClientRect();
      const after = event.clientY > bounds.top + bounds.height / 2;
      list.insertBefore(draggedStep, after ? target.nextSibling : target);
    });

    projectCheckboxes.forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        const checked = projectCheckboxes.filter((item) => item.checked);
        if (checked.length === 0) {
          checkbox.checked = true;
          return;
        }
        if (checked.length > 5) {
          checkbox.checked = false;
          showToast({
            title: "Можно выбрать не больше 5 проектов",
            message: "Уберите один из выбранных проектов, чтобы добавить другой.",
            variant: "error",
            action: "",
          });
          return;
        }
        filterPlaybooks();
      });
    });
    filterPlaybooks();
    refreshIndexes();
  };

  initPipelineBuilder();

  const highlightYamlLine = (line) => {
    const escaped = escapeHtml(line || " ");
    const commentIndex = escaped.indexOf("#");
    const code = commentIndex >= 0 ? escaped.slice(0, commentIndex) : escaped;
    const comment = commentIndex >= 0 ? escaped.slice(commentIndex) : "";
    let highlighted = code
      .replace(/^(\s*)-\s/g, '$1<span class="yaml-token yaml-token--dash">-</span> ')
      .replace(/^(\s*-?\s*)([A-Za-z0-9_.-]+)(\s*:)/, '$1<span class="yaml-token yaml-token--key">$2</span>$3')
      .replace(/(&quot;.*?&quot;|&#039;.*?&#039;)/g, '<span class="yaml-token yaml-token--string">$1</span>')
      .replace(/(:\s*)(true|false|null|yes|no|on|off)\b/gi, '$1<span class="yaml-token yaml-token--bool">$2</span>')
      .replace(/(:\s*)(-?\d+(?:\.\d+)?)\b/g, '$1<span class="yaml-token yaml-token--number">$2</span>');
    if (comment) {
      highlighted += `<span class="yaml-token yaml-token--comment">${comment}</span>`;
    }
    return highlighted;
  };

  const initYamlEditor = (textarea) => {
    if (textarea.closest(".yaml-editor")) {
      return;
    }

    if (window.CodeMirror) {
      const editor = document.createElement("div");
      editor.className = "yaml-editor yaml-editor--cm is-collapsed";
      if (textarea.readOnly) {
        editor.classList.add("yaml-editor--readonly");
      }

      const chrome = document.createElement("div");
      chrome.className = "yaml-editor__chrome";
      chrome.innerHTML = `
        <span><i data-lucide="file-code-2" aria-hidden="true"></i> YAML</span>
        <span>spaces: 2</span>
      `;

      const expandButton = document.createElement("button");
      expandButton.className = "yaml-editor__expand";
      expandButton.type = "button";
      expandButton.innerHTML = '<span>Открыть YAML playbook</span><small>Нажмите, чтобы развернуть редактор</small>';

      textarea.parentNode.insertBefore(editor, textarea);
      editor.appendChild(chrome);
      editor.appendChild(textarea);

      const codeMirror = window.CodeMirror.fromTextArea(textarea, {
        mode: "yaml",
        theme: "material-darker",
        lineNumbers: true,
        lineWrapping: true,
        indentUnit: 2,
        tabSize: 2,
        smartIndent: true,
        readOnly: textarea.readOnly,
        viewportMargin: Infinity,
        extraKeys: {
          Tab(cm) {
            if (textarea.readOnly) {
              return false;
            }
            if (cm.somethingSelected()) {
              cm.indentSelection("add");
            } else {
              cm.replaceSelection("  ", "end");
            }
            return true;
          },
        },
      });

      editor.appendChild(expandButton);
      const setExpanded = (expanded, focus = true) => {
        editor.classList.toggle("is-collapsed", !expanded);
        editor.classList.toggle("is-expanded", expanded);
        expandButton.setAttribute("aria-hidden", expanded ? "true" : "false");
        codeMirror.setSize(null, expanded ? 520 : 168);
        window.requestAnimationFrame(() => {
          codeMirror.refresh();
          if (expanded && focus && !textarea.readOnly) {
            codeMirror.focus();
          }
        });
      };

      codeMirror.on("change", () => codeMirror.save());
      textarea.closest("form")?.addEventListener("submit", () => codeMirror.save());
      expandButton.addEventListener("click", () => setExpanded(true));
      chrome.addEventListener("click", () => setExpanded(true));
      codeMirror.on("focus", () => setExpanded(true, false));
      setExpanded(false, false);

      if (window.lucide) {
        window.lucide.createIcons({ nodes: chrome.querySelectorAll("[data-lucide]") });
      }
      return;
    }

    const editor = document.createElement("div");
    editor.className = "yaml-editor is-collapsed";
    if (textarea.readOnly) {
      editor.classList.add("yaml-editor--readonly");
    }
    textarea.spellcheck = false;
    textarea.autocomplete = "off";
    textarea.setAttribute("autocapitalize", "off");

    const chrome = document.createElement("div");
    chrome.className = "yaml-editor__chrome";
    chrome.innerHTML = `
      <span><i data-lucide="file-code-2" aria-hidden="true"></i> YAML</span>
      <span>spaces: 2</span>
    `;

    const body = document.createElement("div");
    body.className = "yaml-editor__body";
    const gutter = document.createElement("div");
    gutter.className = "yaml-editor__gutter";
    const codeWrap = document.createElement("div");
    codeWrap.className = "yaml-editor__code";
    const highlight = document.createElement("pre");
    highlight.className = "yaml-editor__highlight";
    highlight.setAttribute("aria-hidden", "true");
    const expandButton = document.createElement("button");
    expandButton.className = "yaml-editor__expand";
    expandButton.type = "button";
    expandButton.innerHTML = '<span>Открыть YAML playbook</span><small>Нажмите, чтобы развернуть редактор</small>';

    textarea.parentNode.insertBefore(editor, textarea);
    editor.appendChild(chrome);
    editor.appendChild(body);
    editor.appendChild(expandButton);
    body.appendChild(gutter);
    body.appendChild(codeWrap);
    codeWrap.appendChild(highlight);
    codeWrap.appendChild(textarea);

    const sync = () => {
      const lines = textarea.value.split("\n");
      const lineCount = Math.max(lines.length, 1);
      gutter.innerHTML = Array.from({ length: lineCount }, (_, index) => `<span>${index + 1}</span>`).join("");
      highlight.innerHTML = lines.map((line) => `<span class="yaml-editor__line">${highlightYamlLine(line)}</span>`).join("");
      highlight.style.minHeight = `${textarea.scrollHeight}px`;
      window.requestAnimationFrame(() => {
        const gutterLines = gutter.querySelectorAll("span");
        const codeLines = highlight.querySelectorAll(".yaml-editor__line");
        codeLines.forEach((line, index) => {
          if (gutterLines[index]) {
            gutterLines[index].style.minHeight = `${line.getBoundingClientRect().height}px`;
          }
        });
        syncScroll();
      });
    };

    const syncScroll = () => {
      highlight.scrollTop = textarea.scrollTop;
      highlight.scrollLeft = textarea.scrollLeft;
      gutter.scrollTop = textarea.scrollTop;
    };

    const scheduleSync = () => {
      window.requestAnimationFrame(() => {
        sync();
        syncScroll();
      });
    };

    const expandEditor = (focus = true) => {
      editor.classList.remove("is-collapsed");
      editor.classList.add("is-expanded");
      expandButton.setAttribute("aria-hidden", "true");
      sync();
      syncScroll();
      if (focus && !textarea.readOnly) {
        window.requestAnimationFrame(() => textarea.focus());
      }
    };

    textarea.addEventListener("input", () => {
      sync();
      syncScroll();
      scheduleSync();
    });
    textarea.addEventListener("beforeinput", scheduleSync);
    textarea.addEventListener("paste", scheduleSync);
    textarea.addEventListener("cut", scheduleSync);
    textarea.addEventListener("keyup", scheduleSync);
    textarea.addEventListener("scroll", syncScroll);
    textarea.addEventListener("focus", () => expandEditor(false));
    expandButton.addEventListener("click", () => expandEditor(true));
    chrome.addEventListener("click", () => expandEditor(true));
    textarea.addEventListener("keydown", (event) => {
      if (event.key !== "Tab" || textarea.readOnly) {
        return;
      }
      event.preventDefault();
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      textarea.value = `${textarea.value.slice(0, start)}  ${textarea.value.slice(end)}`;
      textarea.selectionStart = start + 2;
      textarea.selectionEnd = start + 2;
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });

    sync();
    syncScroll();
    if (window.lucide) {
      window.lucide.createIcons({ nodes: chrome.querySelectorAll("[data-lucide]") });
    }
  };

  document.querySelectorAll("textarea[data-yaml-editor]").forEach(initYamlEditor);

  document.querySelectorAll("[data-playbook-file-card]").forEach((card) => {
    const toggle = card.querySelector("[data-playbook-file-toggle]");
    if (!toggle) {
      return;
    }

    const setOpen = (open) => {
      card.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    };

    const switchOpen = () => setOpen(!card.classList.contains("is-open"));

    toggle.addEventListener("click", (event) => {
      if (event.target.closest("form, button, input, textarea, select, a")) {
        return;
      }
      switchOpen();
    });

    toggle.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      if (event.target.closest("form, button, input, textarea, select, a")) {
        return;
      }
      event.preventDefault();
      switchOpen();
    });
  });

  const countdownNodes = document.querySelectorAll("[data-task-countdown]");
  if (countdownNodes.length) {
    const formatCountdown = (target) => {
      const diff = target.getTime() - Date.now();
      if (Number.isNaN(diff)) {
        return "Некорректное время";
      }
      if (diff <= 0) {
        return "Время наступило";
      }
      const totalSeconds = Math.floor(diff / 1000);
      const days = Math.floor(totalSeconds / 86400);
      const hours = Math.floor((totalSeconds % 86400) / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      const seconds = totalSeconds % 60;
      if (days > 0) {
        return `Через ${days} д ${hours} ч ${minutes} мин`;
      }
      if (hours > 0) {
        return `Через ${hours} ч ${minutes} мин ${seconds} с`;
      }
      return `Через ${minutes} мин ${seconds} с`;
    };

    const updateCountdowns = () => {
      countdownNodes.forEach((node) => {
        const target = new Date(node.getAttribute("data-task-countdown"));
        const base = node.getAttribute("data-task-countdown-label");
        node.textContent = base ? `${base} / ${formatCountdown(target)}` : formatCountdown(target);
      });
    };

    countdownNodes.forEach((node) => {
      if (!node.getAttribute("data-task-countdown-label")) {
        node.setAttribute("data-task-countdown-label", node.textContent.trim());
      }
    });
    updateCountdowns();
    window.setInterval(updateCountdowns, 1000);
  }

  const serviceStatus = document.querySelector("[data-health-url]");
  if (serviceStatus) {
    const label = serviceStatus.querySelector("[data-health-text]");
    const healthUrl = serviceStatus.getAttribute("data-health-url");
    const schedulerStatus = document.querySelector("[data-scheduler-status]");
    const schedulerLabel = document.querySelector("[data-scheduler-text]");

    const updateHealth = async () => {
      try {
        const response = await fetch(healthUrl, {
          cache: "no-store",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`HTTP: ${response.status}`);
        }
        const payload = await response.json();
        serviceStatus.classList.remove("service-status--down");
        serviceStatus.classList.add("service-status--up");
        if (label) {
          label.textContent = "Работает (HTTP: OK)";
        }
        if (schedulerStatus && schedulerLabel) {
          const scheduler = payload.scheduler || {};
          const isActive = scheduler.active && !scheduler.last_error;
          schedulerStatus.classList.toggle("service-status--down", !isActive);
          schedulerStatus.classList.toggle("service-status--up", isActive);
          schedulerLabel.textContent = isActive
            ? "Scheduler активен"
            : (scheduler.last_error ? `Ошибка: ${scheduler.last_error}` : "Ожидает первого запуска");
        }
      } catch (error) {
        serviceStatus.classList.remove("service-status--up");
        serviceStatus.classList.add("service-status--down");
        if (label) {
          label.textContent = "Недоступна (HTTP: ERROR)";
        }
        if (schedulerStatus && schedulerLabel) {
          schedulerStatus.classList.remove("service-status--up");
          schedulerStatus.classList.add("service-status--down");
          schedulerLabel.textContent = "Статус недоступен";
        }
      }
    };

    updateHealth();
    window.setInterval(updateHealth, 15000);
  }

  const monitoringPanel = document.querySelector("[data-project-metrics]");
  if (monitoringPanel) {
    const metricsUrl = monitoringPanel.getAttribute("data-project-metrics");
    const updatedLabel = monitoringPanel.querySelector("[data-metrics-updated]");
    const containersRail = document.querySelector("[data-project-containers]");
    const imagesRail = document.querySelector("[data-project-images]");
    const containerCounters = document.querySelectorAll("[data-container-count]");
    const imageCounters = document.querySelectorAll("[data-image-count]");
    const projectId = metricsUrl.match(/\/projects\/(\d+)\/metrics/)?.[1];

    const updateNodeStatuses = (onlineNodeIds) => {
      const online = new Set((onlineNodeIds || []).map((id) => String(id)));
      document.querySelectorAll("[data-project-node-id]").forEach((nodeCard) => {
        const isOnline = online.has(nodeCard.getAttribute("data-project-node-id"));
        const status = nodeCard.querySelector("[data-node-status]");
        nodeCard.classList.toggle("project-node-item--up", isOnline);
        nodeCard.classList.toggle("project-node-item--down", !isOnline);
        nodeCard.classList.toggle("project-hero-runner--up", isOnline);
        nodeCard.classList.toggle("project-hero-runner--down", !isOnline);
        if (status) {
          status.classList.toggle("runner-status--up", isOnline);
          status.classList.toggle("runner-status--down", !isOnline);
          status.innerHTML = `<i></i>${isOnline ? "Активен" : "Не активен"}`;
        }
      });
    };

    const renderContainers = (containers) => {
      if (!containersRail) {
        return;
      }
      const count = containers?.length || 0;
      containerCounters.forEach((counter) => {
        counter.textContent = `${count} контейнеров`;
      });
      if (!containers || containers.length === 0) {
        containersRail.innerHTML = `
          <article class="docker-container-empty">
            <i data-lucide="box" aria-hidden="true"></i>
            <span>Docker-контейнеры не найдены.</span>
          </article>
        `;
        if (window.lucide) {
          window.lucide.createIcons({ nodes: containersRail.querySelectorAll("[data-lucide]") });
        }
        return;
      }
      containersRail.innerHTML = containers.map((container) => {
        const isRunning = container.state === "running";
        const webLinks = Array.isArray(container.web_urls) ? container.web_urls : [];
        const primaryWebLink = webLinks[0] || null;
        const portsMeta = webLinks.length
          ? webLinks.map((link) => `<code>${escapeHtml(link.host_port)}->${escapeHtml(link.container_port)}</code>`).join("")
          : "";
        return `
          <article class="docker-container-card docker-container-card--${isRunning ? "running" : "stopped"}">
            <div class="docker-container-card__top">
              <span class="docker-container-card__icon docker-container-card__icon--${isRunning ? "live" : "idle"}">
                <i data-lucide="${isRunning ? "container" : "package-open"}" aria-hidden="true"></i>
              </span>
              <span class="runner-status runner-status--${isRunning ? "up" : "down"}">
                <i></i>${escapeHtml(container.status || (isRunning ? "running" : "stopped"))}
              </span>
            </div>
            <div class="docker-container-card__body">
              <strong>${escapeHtml(container.name)}</strong>
              <span>${escapeHtml(container.image || "Не указан")}</span>
            </div>
            <div class="docker-container-card__meta">
              <span>${escapeHtml(container.node_name)}</span>
              <code>${escapeHtml(container.server_ip)}</code>
              <code>${escapeHtml(container.id || "-")}</code>
              ${portsMeta}
            </div>
            <div class="docker-container-card__actions">
              ${primaryWebLink ? `
                <a class="container-action container-action--open" href="${escapeHtml(primaryWebLink.url)}" target="_blank" rel="noopener noreferrer" title="Открыть ${escapeHtml(primaryWebLink.label)}">
                  <i data-lucide="external-link" aria-hidden="true"></i>
                </a>
              ` : ""}
              <button class="container-action container-action--files" type="button" title="Файлы контейнера" data-container-files data-node-id="${escapeHtml(container.node_id)}" data-container-id="${escapeHtml(container.id)}" data-container-name="${escapeHtml(container.name)}" data-node-name="${escapeHtml(container.node_name)}" ${isRunning ? "" : "disabled"}>
                <i data-lucide="folder-tree" aria-hidden="true"></i>
              </button>
              <button class="container-action container-action--logs" type="button" title="Показать логи" data-container-logs data-node-id="${escapeHtml(container.node_id)}" data-container-id="${escapeHtml(container.id)}" data-container-name="${escapeHtml(container.name)}" data-node-name="${escapeHtml(container.node_name)}">
                <i data-lucide="square-terminal" aria-hidden="true"></i>
              </button>
              <button class="container-action container-action--restart" type="button" title="Перезагрузить" data-container-action="restart" data-node-id="${escapeHtml(container.node_id)}" data-container-id="${escapeHtml(container.id)}" ${isRunning ? "" : "disabled"}>
                <i data-lucide="rotate-cw" aria-hidden="true"></i>
              </button>
              <button class="container-action container-action--stop" type="button" title="Остановить" data-container-action="stop" data-node-id="${escapeHtml(container.node_id)}" data-container-id="${escapeHtml(container.id)}" ${isRunning ? "" : "disabled"}>
                <i data-lucide="circle-stop" aria-hidden="true"></i>
              </button>
              <button class="container-action container-action--delete" type="button" title="Удалить" data-container-action="delete" data-node-id="${escapeHtml(container.node_id)}" data-container-id="${escapeHtml(container.id)}">
                <i data-lucide="trash-2" aria-hidden="true"></i>
              </button>
            </div>
          </article>
        `;
      }).join("");
      if (window.lucide) {
        window.lucide.createIcons({ nodes: containersRail.querySelectorAll("[data-lucide]") });
      }
    };

    const renderImages = (images) => {
      if (!imagesRail) {
        return;
      }
      const count = images?.length || 0;
      imageCounters.forEach((counter) => {
        counter.textContent = `${count} образов`;
      });
      if (!images || images.length === 0) {
        imagesRail.innerHTML = `
          <article class="docker-container-empty">
            <i data-lucide="layers-3" aria-hidden="true"></i>
            <span>Docker-образы не найдены.</span>
          </article>
        `;
        if (window.lucide) {
          window.lucide.createIcons({ nodes: imagesRail.querySelectorAll("[data-lucide]") });
        }
        return;
      }
      imagesRail.innerHTML = images.map((image) => {
        const repo = image.repository && image.repository !== "<none>" ? image.repository : "untagged";
        const tag = image.tag && image.tag !== "<none>" ? image.tag : "none";
        return `
          <article class="docker-container-card docker-image-card">
            <div class="docker-container-card__top">
              <span class="docker-container-card__icon docker-image-card__icon">
                <i data-lucide="layers-3" aria-hidden="true"></i>
              </span>
              <span class="runner-status runner-status--up">
                <i></i>${escapeHtml(image.size || "image")}
              </span>
            </div>
            <div class="docker-container-card__body">
              <strong>${escapeHtml(repo)}:${escapeHtml(tag)}</strong>
              <span>${escapeHtml(image.created_since || "created unknown")}</span>
            </div>
            <div class="docker-container-card__meta">
              <span>${escapeHtml(image.node_name)}</span>
              <code>${escapeHtml(image.server_ip)}</code>
              <code>${escapeHtml(image.id || "-")}</code>
            </div>
            <div class="docker-container-card__actions">
              <button class="container-action container-action--delete" type="button" title="Удалить образ" data-image-action="delete" data-node-id="${escapeHtml(image.node_id)}" data-image-id="${escapeHtml(image.id)}">
                <i data-lucide="trash-2" aria-hidden="true"></i>
              </button>
            </div>
          </article>
        `;
      }).join("");
      if (window.lucide) {
        window.lucide.createIcons({ nodes: imagesRail.querySelectorAll("[data-lucide]") });
      }
    };

    const containerFilesDialog = document.getElementById("container-files-dialog");
    const containerFilesState = {
      nodeId: "",
      containerId: "",
      containerName: "",
      nodeName: "",
      path: "/",
    };

    const normalizeContainerPath = (path) => {
      const value = String(path || "/").trim().replace(/\\/g, "/");
      const parts = [];
      for (const part of value.split("/")) {
        if (!part || part === ".") {
          continue;
        }
        if (part === "..") {
          parts.pop();
          continue;
        }
        parts.push(part);
      }
      return `/${parts.join("/")}`;
    };

    const containerParentPath = (path) => {
      const normalized = normalizeContainerPath(path);
      if (normalized === "/") {
        return "/";
      }
      return normalized.slice(0, normalized.lastIndexOf("/")) || "/";
    };

    const setContainerFilesStatus = (message) => {
      const status = containerFilesDialog?.querySelector("[data-container-files-status]");
      if (status) {
        status.textContent = message;
      }
    };

    const renderContainerFilePayload = (payload) => {
      const list = containerFilesDialog?.querySelector("[data-container-files-list]");
      const output = containerFilesDialog?.querySelector("[data-container-files-output]");
      const current = containerFilesDialog?.querySelector("[data-container-files-current]");
      const pathInput = containerFilesDialog?.querySelector("[data-container-files-path]");
      if (!list || !output) {
        return;
      }

      containerFilesState.path = normalizeContainerPath(payload.path || containerFilesState.path);
      if (pathInput) {
        pathInput.value = containerFilesState.path;
      }
      if (current) {
        current.textContent = containerFilesState.path;
      }

      if (payload.type === "directory") {
        const entries = payload.entries || [];
        output.textContent = "Выберите файл, чтобы посмотреть содержимое.";
        list.innerHTML = entries.length
          ? entries.map((entry) => {
              const isDirectory = entry.type === "directory";
              const icon = isDirectory ? "folder" : entry.type === "link" ? "link" : "file";
              const size = isDirectory ? "папка" : entry.size === "-" ? "файл" : `${entry.size} B`;
              const nextPath = normalizeContainerPath(`${containerFilesState.path}/${entry.name}`);
              return `
                <button class="container-files-entry container-files-entry--${escapeHtml(entry.type)}" type="button" data-container-file-path="${escapeHtml(nextPath)}">
                  <i data-lucide="${icon}" aria-hidden="true"></i>
                  <span>${escapeHtml(entry.name)}</span>
                  <small>${escapeHtml(size)}</small>
                </button>
              `;
            }).join("")
          : `<div class="docker-container-empty">Папка пустая.</div>`;
        setContainerFilesStatus(`${entries.length} элементов`);
      } else {
        const parentPath = containerParentPath(containerFilesState.path);
        list.innerHTML = `
          <button class="container-files-entry" type="button" data-container-file-path="${escapeHtml(parentPath)}">
            <i data-lucide="arrow-up" aria-hidden="true"></i>
            <span>Вернуться в папку</span>
            <small>${escapeHtml(parentPath)}</small>
          </button>
        `;
        output.textContent = payload.content || "Файл пустой.";
        setContainerFilesStatus(payload.truncated ? "Показаны первые 256 KB" : `${payload.size || 0} B`);
      }

      if (window.lucide) {
        window.lucide.createIcons({ nodes: containerFilesDialog.querySelectorAll("[data-lucide]") });
      }
    };

    const loadContainerPath = async (path) => {
      if (!projectId || !containerFilesState.nodeId || !containerFilesState.containerId) {
        return;
      }

      const normalizedPath = normalizeContainerPath(path);
      const output = containerFilesDialog?.querySelector("[data-container-files-output]");
      if (output) {
        output.textContent = "Загружаю содержимое контейнера...";
      }
      setContainerFilesStatus("Загрузка");

      const response = await fetch(`/dashboard/projects/${projectId}/containers/${encodeURIComponent(containerFilesState.nodeId)}/${encodeURIComponent(containerFilesState.containerId)}/files?path=${encodeURIComponent(normalizedPath)}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        let detail = `HTTP: ${response.status}`;
        try {
          const errorPayload = await response.json();
          detail = errorPayload.detail || detail;
        } catch (error) {
          detail = `HTTP: ${response.status}`;
        }
        throw new Error(detail);
      }
      renderContainerFilePayload(await response.json());
    };

    const openContainerFiles = async (button) => {
      if (!projectId || button.disabled) {
        return;
      }
      containerFilesState.nodeId = button.getAttribute("data-node-id") || "";
      containerFilesState.containerId = button.getAttribute("data-container-id") || "";
      containerFilesState.containerName = button.getAttribute("data-container-name") || containerFilesState.containerId;
      containerFilesState.nodeName = button.getAttribute("data-node-name") || "";
      containerFilesState.path = "/";
      if (!containerFilesState.nodeId || !containerFilesState.containerId || !containerFilesDialog) {
        return;
      }

      const title = containerFilesDialog.querySelector("[data-container-files-title]");
      const meta = containerFilesDialog.querySelector("[data-container-files-meta]");
      const pathInput = containerFilesDialog.querySelector("[data-container-files-path]");
      const list = containerFilesDialog.querySelector("[data-container-files-list]");
      const output = containerFilesDialog.querySelector("[data-container-files-output]");
      if (title) {
        title.textContent = `Файлы ${containerFilesState.containerName}`;
      }
      if (meta) {
        meta.textContent = `${containerFilesState.nodeName} · ${containerFilesState.containerId}`;
      }
      if (pathInput) {
        pathInput.value = "/";
      }
      if (list) {
        list.innerHTML = `<div class="docker-container-empty">Загрузка...</div>`;
      }
      if (output) {
        output.textContent = "Загружаю / ...";
      }
      if (typeof containerFilesDialog.showModal === "function" && !containerFilesDialog.open) {
        containerFilesDialog.showModal();
      }

      button.disabled = true;
      try {
        await loadContainerPath("/");
      } catch (error) {
        if (output) {
          output.textContent = error.message || "Docker вернул ошибку при чтении файлов.";
        }
        setContainerFilesStatus("Ошибка");
        showToast({
          title: "Не удалось прочитать файлы контейнера",
          message: error.message || "Docker вернул ошибку.",
          href: "/docs/docker-access",
        });
      } finally {
        button.disabled = false;
      }
    };

    const openContainerLogs = async (button) => {
      if (!projectId || button.disabled) {
        return;
      }
      const nodeId = button.getAttribute("data-node-id");
      const containerId = button.getAttribute("data-container-id");
      const containerName = button.getAttribute("data-container-name") || containerId;
      const nodeName = button.getAttribute("data-node-name") || "";
      if (!nodeId || !containerId) {
        return;
      }

      const dialog = document.getElementById("container-logs-dialog");
      const title = dialog?.querySelector("[data-container-logs-title]");
      const meta = dialog?.querySelector("[data-container-logs-meta]");
      const status = dialog?.querySelector("[data-container-logs-status]");
      const output = dialog?.querySelector("[data-container-logs-output]");
      if (!dialog || !output) {
        return;
      }

      if (title) {
        title.textContent = `Логи ${containerName}`;
      }
      if (meta) {
        meta.textContent = `${nodeName} · ${containerId}`;
      }
      if (status) {
        status.textContent = "Загрузка";
      }
      output.textContent = "Загружаю docker logs...";
      if (typeof dialog.showModal === "function" && !dialog.open) {
        dialog.showModal();
      }

      button.disabled = true;
      try {
        const response = await fetch(`/dashboard/projects/${projectId}/containers/${encodeURIComponent(nodeId)}/${encodeURIComponent(containerId)}/logs?tail=300`, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          let detail = `HTTP: ${response.status}`;
          try {
            const errorPayload = await response.json();
            detail = errorPayload.detail || detail;
          } catch (error) {
            detail = `HTTP: ${response.status}`;
          }
          throw new Error(detail);
        }
        const payload = await response.json();
        output.textContent = payload.logs || "Логи контейнера пустые.";
        if (status) {
          status.textContent = `${payload.tail || 300} строк`;
        }
      } catch (error) {
        output.textContent = error.message || "Docker вернул ошибку при чтении логов.";
        if (status) {
          status.textContent = "Ошибка";
        }
        showToast({
          title: "Не удалось прочитать логи контейнера",
          message: error.message || "Docker вернул ошибку.",
          href: "/docs/docker-access",
        });
      } finally {
        button.disabled = false;
      }
    };

    const runContainerAction = async (button) => {
      if (!projectId || button.disabled) {
        return;
      }
      const action = button.getAttribute("data-container-action");
      const nodeId = button.getAttribute("data-node-id");
      const containerId = button.getAttribute("data-container-id");
      if (!action || !nodeId || !containerId) {
        return;
      }
      if (action === "delete" && !window.confirm("Удалить контейнер? Действие нельзя отменить.")) {
        return;
      }

      const actionLabels = {
        stop: {
          success: "Контейнер остановлен",
          error: "Не удалось остановить контейнер",
        },
        restart: {
          success: "Контейнер перезагружен",
          error: "Не удалось перезагрузить контейнер",
        },
        delete: {
          success: "Контейнер удален",
          error: "Не удалось удалить контейнер",
        },
      };
      const labels = actionLabels[action] || {
        success: "Действие выполнено",
        error: "Не удалось выполнить действие",
      };

      button.disabled = true;
      try {
        const response = await fetch(`/dashboard/projects/${projectId}/containers/${encodeURIComponent(nodeId)}/${encodeURIComponent(containerId)}/${action}`, {
          method: "POST",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          let detail = `HTTP: ${response.status}`;
          try {
            const errorPayload = await response.json();
            detail = errorPayload.detail || detail;
          } catch (error) {
            detail = `HTTP: ${response.status}`;
          }
          throw new Error(detail);
        }
        showToast({
          title: labels.success,
          message: containerId,
          variant: "success",
          action: "",
        });
        await updateProjectMetrics();
      } catch (error) {
        showToast({
          title: labels.error,
          message: error.message || "Docker вернул ошибку.",
          href: "/docs/docker-access",
        });
        button.disabled = false;
      }
    };

    containerFilesDialog?.querySelector("[data-container-files-list]")?.addEventListener("click", async (event) => {
      const entry = event.target.closest("[data-container-file-path]");
      if (!entry) {
        return;
      }
      try {
        await loadContainerPath(entry.getAttribute("data-container-file-path"));
      } catch (error) {
        const output = containerFilesDialog.querySelector("[data-container-files-output]");
        if (output) {
          output.textContent = error.message || "Docker вернул ошибку при чтении файлов.";
        }
        setContainerFilesStatus("Ошибка");
      }
    });

    containerFilesDialog?.querySelector("[data-container-files-refresh]")?.addEventListener("click", async () => {
      try {
        await loadContainerPath(containerFilesDialog.querySelector("[data-container-files-path]")?.value || containerFilesState.path);
      } catch (error) {
        const output = containerFilesDialog.querySelector("[data-container-files-output]");
        if (output) {
          output.textContent = error.message || "Docker вернул ошибку при чтении файлов.";
        }
        setContainerFilesStatus("Ошибка");
      }
    });

    containerFilesDialog?.querySelector("[data-container-files-up]")?.addEventListener("click", async () => {
      try {
        await loadContainerPath(containerParentPath(containerFilesDialog.querySelector("[data-container-files-path]")?.value || containerFilesState.path));
      } catch (error) {
        const output = containerFilesDialog.querySelector("[data-container-files-output]");
        if (output) {
          output.textContent = error.message || "Docker вернул ошибку при чтении файлов.";
        }
        setContainerFilesStatus("Ошибка");
      }
    });

    containerFilesDialog?.querySelector("[data-container-files-path]")?.addEventListener("keydown", async (event) => {
      if (event.key !== "Enter") {
        return;
      }
      event.preventDefault();
      try {
        await loadContainerPath(event.currentTarget.value);
      } catch (error) {
        const output = containerFilesDialog.querySelector("[data-container-files-output]");
        if (output) {
          output.textContent = error.message || "Docker вернул ошибку при чтении файлов.";
        }
        setContainerFilesStatus("Ошибка");
      }
    });

    containersRail?.addEventListener("click", (event) => {
      const filesButton = event.target.closest("[data-container-files]");
      if (filesButton) {
        openContainerFiles(filesButton);
        return;
      }
      const logsButton = event.target.closest("[data-container-logs]");
      if (logsButton) {
        openContainerLogs(logsButton);
        return;
      }
      const button = event.target.closest("[data-container-action]");
      if (button) {
        runContainerAction(button);
      }
    });

    const runImageAction = async (button) => {
      if (!projectId || button.disabled) {
        return;
      }
      const nodeId = button.getAttribute("data-node-id");
      const imageId = button.getAttribute("data-image-id");
      if (!nodeId || !imageId) {
        return;
      }
      if (!window.confirm("Удалить Docker image? Действие нельзя отменить.")) {
        return;
      }

      button.disabled = true;
      try {
        const response = await fetch(`/dashboard/projects/${projectId}/images/${encodeURIComponent(nodeId)}/${encodeURIComponent(imageId)}/delete`, {
          method: "POST",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          let detail = `HTTP: ${response.status}`;
          try {
            const errorPayload = await response.json();
            detail = errorPayload.detail || detail;
          } catch (error) {
            detail = `HTTP: ${response.status}`;
          }
          throw new Error(detail);
        }
        showToast({
          title: "Образ удален",
          message: imageId,
          variant: "success",
          action: "",
        });
        await updateProjectMetrics();
      } catch (error) {
        showToast({
          title: "Не удалось удалить образ",
          message: error.message || "Docker вернул ошибку.",
          href: "/docs/docker-access",
        });
        button.disabled = false;
      }
    };

    imagesRail?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-image-action]");
      if (button) {
        runImageAction(button);
      }
    });

    const drawChart = (container, points, maxValue) => {
      const width = 320;
      const height = 112;
      const padding = 8;
      const max = Math.max(maxValue || 100, ...points, 1);
      const step = (width - padding * 2) / Math.max(points.length - 1, 1);
      const coords = points.map((point, index) => {
        const x = padding + index * step;
        const y = height - padding - (point / max) * (height - padding * 2);
        return [x, y];
      });
      const line = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
      const area = `${padding},${height - padding} ${line} ${width - padding},${height - padding}`;

      container.innerHTML = `
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-hidden="true">
          <g class="monitoring-chart__grid">
            <line x1="0" y1="28" x2="${width}" y2="28"></line>
            <line x1="0" y1="56" x2="${width}" y2="56"></line>
            <line x1="0" y1="84" x2="${width}" y2="84"></line>
          </g>
          <polygon class="monitoring-chart__area" points="${area}"></polygon>
          <polyline class="monitoring-chart__line" points="${line}"></polyline>
        </svg>
      `;
    };

    const updateProjectMetrics = async () => {
      try {
        const response = await fetch(metricsUrl, {
          cache: "no-store",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          let detail = `HTTP: ${response.status}`;
          try {
            const errorPayload = await response.json();
            detail = errorPayload.detail || detail;
          } catch (error) {
            detail = `HTTP: ${response.status}`;
          }
          throw new Error(detail);
        }
        const payload = await response.json();
        updateNodeStatuses(payload.online_node_ids);
        renderContainers(payload.containers);
        renderImages(payload.images);
        payload.metrics.forEach((metric) => {
          const card = monitoringPanel.querySelector(`[data-metric-card="${metric.key}"]`);
          if (!card) {
            return;
          }
          const value = card.querySelector("[data-metric-value]");
          const chart = card.querySelector("[data-metric-chart]");
          const fill = card.querySelector("[data-metric-fill]");
          const details = card.querySelector("[data-metric-details]");
          if (value) {
            value.textContent = `${metric.current}${metric.unit}`;
          }
          if (chart) {
            drawChart(chart, metric.points, metric.max);
          }
          if (fill) {
            fill.style.width = `${Math.max(0, Math.min(100, Number(metric.fill || 0)))}%`;
          }
          if (details) {
            details.innerHTML = (metric.details || []).map((item) => `
              <span class="monitoring-card__detail">
                <small>${escapeHtml(item.label)}</small>
                <strong>${escapeHtml(item.value)}</strong>
              </span>
            `).join("");
          }
        });
        if (updatedLabel) {
          updatedLabel.textContent = payload.errors && payload.errors.length
            ? payload.errors[0]
            : "Обновлено сейчас";
        }
        if (payload.errors && payload.errors.length) {
          showToast({
            title: "Docker не отдает контейнеры",
            message: payload.errors[0],
            href: "/docs/docker-access",
          });
        }
        monitoringPanel.classList.remove("monitoring-panel--error");
      } catch (error) {
        if (updatedLabel) {
          updatedLabel.textContent = error.message || "Нет данных";
        }
        showToast({
          title: "Метрики недоступны",
          message: error.message || "Airdock не смог получить данные с курьера.",
          href: "/docs/docker-access",
        });
        monitoringPanel.classList.add("monitoring-panel--error");
      }
    };

    updateProjectMetrics();
    window.setInterval(updateProjectMetrics, 10000);
  }

  const analyticsPanel = document.querySelector("[data-analytics-metrics]");
  if (analyticsPanel) {
    const metricsUrl = analyticsPanel.getAttribute("data-analytics-metrics");
    const updatedLabel = document.querySelector("[data-analytics-updated]");
    const statusLabel = analyticsPanel.querySelector("[data-analytics-status]");
    const nodesList = analyticsPanel.querySelector("[data-analytics-nodes]");

    const setAnalyticsValue = (key, value, suffix = "") => {
      document.querySelectorAll(`[data-analytics-value="${key}"]`).forEach((element) => {
        element.textContent = `${value}${suffix}`;
      });
    };

    const setAnalyticsFill = (key, value) => {
      const percent = Math.max(0, Math.min(100, Number(value || 0)));
      document.querySelectorAll(`[data-analytics-fill="${key}"]`).forEach((element) => {
        element.style.width = `${percent}%`;
      });
    };

    const renderAnalyticsNodes = (nodes) => {
      if (!nodesList) {
        return;
      }
      if (!nodes || nodes.length === 0) {
        nodesList.innerHTML = `
          <article class="docker-container-empty">
            <i data-lucide="radio-tower" aria-hidden="true"></i>
            <span>Курьеры пока не созданы.</span>
          </article>
        `;
        if (window.lucide) {
          window.lucide.createIcons({ nodes: nodesList.querySelectorAll("[data-lucide]") });
        }
        return;
      }
      nodesList.innerHTML = nodes.map((node) => {
        const online = node.status === "up";
        const cpu = Number(node.cpu || 0);
        const ram = Number(node.ram || 0);
        const disk = Number(node.disk || 0);
        const services = Number(node.services || 0);
        return `
          <article class="analytics-node analytics-node--${online ? "up" : "down"}">
            <div class="analytics-node__identity">
              <span class="analytics-node__icon"><i data-lucide="radio-tower" aria-hidden="true"></i></span>
              <div>
                <span class="runner-status runner-status--${online ? "up" : "down"}">
                  <i></i>${online ? "Онлайн" : "Нет связи"}
                </span>
                <strong>${escapeHtml(node.name)}</strong>
                <small>${escapeHtml(node.server_ip)}</small>
                <dl>
                  <div><dt>Uptime</dt><dd>${escapeHtml(node.uptime || "—")}</dd></div>
                  <div><dt>Последняя активность</dt><dd>${online ? "сейчас" : "—"}</dd></div>
                  <div><dt>Версия агента</dt><dd>—</dd></div>
                </dl>
              </div>
            </div>
            <div class="analytics-node__metrics">
              <div class="analytics-node-metric analytics-node-metric--violet">
                <span>CPU</span>
                <strong>${cpu.toFixed(1)}%</strong>
                <div class="mini-line" aria-hidden="true"><i style="background: linear-gradient(90deg, #8b5cf6 ${Math.min(cpu, 100)}%, rgba(139, 92, 246, 0.12) ${Math.min(cpu, 100)}%)"></i></div>
                <small>Средняя загрузка</small>
              </div>
              <div class="analytics-node-metric analytics-node-metric--blue">
                <span>RAM</span>
                <strong>${ram.toFixed(1)}%</strong>
                <div class="mini-line" aria-hidden="true"><i style="background: linear-gradient(90deg, #2563eb ${Math.min(ram, 100)}%, rgba(37, 99, 235, 0.14) ${Math.min(ram, 100)}%)"></i></div>
                <small>Использовано</small>
              </div>
              <div class="analytics-node-metric analytics-node-metric--cyan">
                <span>Диск</span>
                <strong>${disk.toFixed(1)}%</strong>
                <div class="mini-line" aria-hidden="true"><i style="background: linear-gradient(90deg, #22d3ee ${Math.min(disk, 100)}%, rgba(34, 211, 238, 0.14) ${Math.min(disk, 100)}%)"></i></div>
                <small>Занято</small>
              </div>
              <div class="analytics-node-metric analytics-node-metric--violet">
                <span>Процессы</span>
                <strong>${services}</strong>
                <div class="mini-line" aria-hidden="true"><i></i></div>
                <small>Активных</small>
              </div>
            </div>
            <div class="analytics-node__footer">
              <span><i data-lucide="info" aria-hidden="true"></i>ОС: Ubuntu 22.04.4 LTS</span>
              <span><i data-lucide="timer" aria-hidden="true"></i>Uptime: ${escapeHtml(node.uptime || "—")}</span>
              <span><i data-lucide="box" aria-hidden="true"></i>Docker: доступен</span>
              <span><i data-lucide="check-circle-2" aria-hidden="true"></i>Статус: ${online ? "Здоров" : "Нет связи"}</span>
            </div>
          </article>
        `;
      }).join("");
      if (window.lucide) {
        window.lucide.createIcons({ nodes: nodesList.querySelectorAll("[data-lucide]") });
      }
    };

    const updateAnalyticsMetrics = async () => {
      try {
        const response = await fetch(metricsUrl, {
          cache: "no-store",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`HTTP: ${response.status}`);
        }
        const payload = await response.json();
        const metrics = payload.metrics || {};
        setAnalyticsValue("nodes", `${payload.nodes_online || 0} / ${payload.nodes_total || 0}`);
        setAnalyticsValue("cpu", Number(metrics.cpu || 0).toFixed(1), "%");
        setAnalyticsValue("ram", Number(metrics.ram || 0).toFixed(1), "%");
        setAnalyticsValue("disk", Number(metrics.disk || 0).toFixed(1), "%");
        setAnalyticsValue("services", metrics.services || 0);
        setAnalyticsValue("tasks", metrics.tasks || 0);
        document.querySelectorAll('[data-analytics-chip="cpu"]').forEach((element) => {
          element.textContent = `${Number(metrics.cpu || 0).toFixed(1)}% avg`;
        });
        document.querySelectorAll('[data-analytics-chip="ram"]').forEach((element) => {
          element.textContent = `${Number(metrics.ram || 0).toFixed(1)}% avg`;
        });
        setAnalyticsFill("cpu", metrics.cpu);
        setAnalyticsFill("ram", metrics.ram);
        setAnalyticsFill("disk", metrics.disk);
        setAnalyticsFill("tasks", Math.min(Number(metrics.tasks || 0), 100));
        renderAnalyticsNodes(payload.nodes);
        if (updatedLabel) {
          updatedLabel.textContent = payload.errors?.length ? payload.errors[0] : "Метрики обновлены";
        }
        if (statusLabel) {
          const hasOnline = Number(payload.nodes_online || 0) > 0;
          statusLabel.classList.toggle("runner-status--up", hasOnline);
          statusLabel.classList.toggle("runner-status--down", !hasOnline);
          statusLabel.innerHTML = `<i></i>${hasOnline ? "Курьеры отвечают" : "Нет доступных курьеров"}`;
        }
      } catch (error) {
        if (updatedLabel) {
          updatedLabel.textContent = error.message || "Метрики недоступны";
        }
        if (statusLabel) {
          statusLabel.classList.remove("runner-status--up");
          statusLabel.classList.add("runner-status--down");
          statusLabel.innerHTML = "<i></i>Ошибка метрик";
        }
      }
    };

    document.querySelectorAll("[data-analytics-refresh]").forEach((button) => {
      button.addEventListener("click", updateAnalyticsMetrics);
    });

    updateAnalyticsMetrics();
    window.setInterval(updateAnalyticsMetrics, 15000);
  }

  const ollamaChat = document.querySelector("[data-ollama-chat]");
  if (ollamaChat) {
    const storageKey = "airdock.ollamaServers";
    const sessionsKey = "airdock.ollamaChatSessions";
    const activeSessionKey = "airdock.ollamaActiveChat";
    const serverForm = ollamaChat.querySelector("[data-ollama-server-form]");
    const serverSelect = ollamaChat.querySelector("[data-ollama-server-select]");
    const modelSelect = ollamaChat.querySelector("[data-ollama-model-select]");
    const refreshModelsButton = ollamaChat.querySelector("[data-ollama-refresh-models]");
    const removeServerButton = ollamaChat.querySelector("[data-ollama-remove-server]");
    const newChatButton = ollamaChat.querySelector("[data-ollama-new-chat]");
    const clearChatButton = ollamaChat.querySelector("[data-ollama-clear-chat]");
    const exportChatButton = ollamaChat.querySelector("[data-ollama-export-chat]");
    const exportAllButton = ollamaChat.querySelector("[data-ollama-export-all]");
    const importChatButton = ollamaChat.querySelector("[data-ollama-import-chat]");
    const importFileInput = ollamaChat.querySelector("[data-ollama-import-file]");
    const sessionList = ollamaChat.querySelector("[data-ollama-session-list]");
    const activeTitle = ollamaChat.querySelector("[data-ollama-active-title]");
    const activeMeta = ollamaChat.querySelector("[data-ollama-active-meta]");
    const composeForm = ollamaChat.querySelector("[data-ollama-compose]");
    const messageInput = composeForm?.querySelector("textarea[name='message']");
    const messagesList = ollamaChat.querySelector("[data-ollama-messages]");
    const statusLabel = ollamaChat.querySelector("[data-ollama-status]");

    const defaultServers = [{ name: "Локальный Ollama", url: "http://localhost:11434" }];
    const starterMessage = "Добавьте сервер Ollama или используйте локальный адрес, затем выберите модель.";
    const thinkingTexts = [
      "Смотрю на задачу под разными углами...",
      "Собираю контекст в связную картину...",
      "Проверяю, где может быть подвох...",
      "Сравниваю варианты ответа...",
      "Уточняю ход рассуждения...",
      "Отбрасываю слабые гипотезы...",
      "Ищу самый полезный ответ...",
      "Складываю детали в аккуратный вывод...",
      "Проверяю формулировки перед ответом...",
      "Думаю, как сказать это яснее...",
    ];

    const readServers = () => {
      try {
        const parsed = JSON.parse(window.localStorage.getItem(storageKey) || "[]");
        return Array.isArray(parsed) && parsed.length ? parsed : defaultServers;
      } catch (error) {
        return defaultServers;
      }
    };

    let servers = readServers();
    let sessions = [];
    let activeSessionId = "";

    const writeServers = () => {
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(servers));
      } catch (error) {
        // Local storage can be unavailable in private mode.
      }
    };

    const uid = () => {
      if (window.crypto?.randomUUID) {
        return window.crypto.randomUUID();
      }
      return `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    };

    const nowIso = () => new Date().toISOString();

    const compactDate = (value) => {
      const date = value ? new Date(value) : new Date();
      if (Number.isNaN(date.getTime())) {
        return "";
      }
      return date.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    };

    const randomThinkingText = (previous = "") => {
      const variants = thinkingTexts.filter((text) => text !== previous);
      return variants[Math.floor(Math.random() * variants.length)] || thinkingTexts[0];
    };

    const chatTitleFrom = (content) => {
      const title = String(content || "").replace(/\s+/g, " ").trim();
      return title ? title.slice(0, 48) : "Новый чат";
    };

    const normalizeSession = (session) => {
      const createdAt = session?.createdAt || nowIso();
      const messages = Array.isArray(session?.messages)
        ? session.messages
            .filter((message) => message && ["user", "assistant", "system"].includes(message.role) && message.content)
            .map((message) => ({
              role: message.role,
              content: String(message.content),
              createdAt: message.createdAt || createdAt,
            }))
        : [];
      return {
        id: String(session?.id || uid()),
        title: String(session?.title || (messages[0] ? chatTitleFrom(messages[0].content) : "Новый чат")),
        serverUrl: String(session?.serverUrl || ""),
        model: String(session?.model || ""),
        messages,
        createdAt,
        updatedAt: session?.updatedAt || createdAt,
      };
    };

    const createSession = () => normalizeSession({ id: uid(), title: "Новый чат", createdAt: nowIso(), updatedAt: nowIso() });

    const readSessions = () => {
      try {
        const parsed = JSON.parse(window.localStorage.getItem(sessionsKey) || "[]");
        if (Array.isArray(parsed) && parsed.length) {
          return parsed.map(normalizeSession);
        }
      } catch (error) {
        // Keep a blank chat if saved history is unreadable.
      }
      return [createSession()];
    };

    const writeSessions = () => {
      try {
        window.localStorage.setItem(sessionsKey, JSON.stringify(sessions));
        window.localStorage.setItem(activeSessionKey, activeSessionId);
      } catch (error) {
        showToast({
          title: "История не сохранена",
          message: "Браузер не дал записать чат в localStorage.",
          variant: "error",
          action: "",
        });
      }
    };

    const currentSession = () => sessions.find((session) => session.id === activeSessionId) || sessions[0];

    const ensureActiveSession = () => {
      sessions = readSessions();
      try {
        activeSessionId = window.localStorage.getItem(activeSessionKey) || "";
      } catch (error) {
        activeSessionId = "";
      }
      if (!sessions.some((session) => session.id === activeSessionId)) {
        activeSessionId = sessions[0].id;
      }
    };

    const selectedServer = () => servers.find((server) => server.url === serverSelect?.value) || servers[0];

    const setStatus = (text, tone = "muted") => {
      if (!statusLabel) {
        return;
      }
      statusLabel.classList.toggle("ollama-chat-status--ok", tone === "ok");
      statusLabel.classList.toggle("ollama-chat-status--error", tone === "error");
      statusLabel.innerHTML = `<i></i>${escapeHtml(text)}`;
    };

    const renderSessionList = () => {
      if (!sessionList) {
        return;
      }
      sessionList.innerHTML = sessions
        .slice()
        .sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)))
        .map((session) => {
          const last = session.messages.at(-1);
          const preview = last ? last.content : "Пустой чат";
          const count = session.messages.length;
          return `
            <article class="ollama-chat-session ${session.id === activeSessionId ? "is-active" : ""}" data-chat-session-id="${escapeHtml(session.id)}">
              <button class="ollama-chat-session__main" type="button" data-open-chat-session="${escapeHtml(session.id)}">
                <strong>${escapeHtml(session.title)}</strong>
                <span>${escapeHtml(preview)}</span>
                <small>${compactDate(session.updatedAt)} · ${count} сообщ.</small>
              </button>
              <button class="ollama-chat-session__delete" type="button" title="Удалить чат" data-delete-chat-session="${escapeHtml(session.id)}">
                <i data-lucide="x" aria-hidden="true"></i>
              </button>
            </article>
          `;
        })
        .join("");
      if (window.lucide) {
        window.lucide.createIcons({ nodes: sessionList.querySelectorAll("[data-lucide]") });
      }
    };

    const renderActiveHeader = () => {
      const session = currentSession();
      if (!session) {
        return;
      }
      if (activeTitle) {
        activeTitle.textContent = session.title;
      }
      if (activeMeta) {
        const server = servers.find((item) => item.url === session.serverUrl)?.name || selectedServer()?.name || "Ollama";
        activeMeta.textContent = `${server}${session.model ? ` · ${session.model}` : ""}`;
      }
    };

    const renderMessages = () => {
      const session = currentSession();
      if (!messagesList || !session) {
        return;
      }
      messagesList.innerHTML = "";
      if (!session.messages.length) {
        appendMessage("assistant", starterMessage, false, false);
      } else {
        session.messages.forEach((message) => appendMessage(message.role, message.content, false, false, message.createdAt));
      }
      messagesList.scrollTop = messagesList.scrollHeight;
      renderActiveHeader();
    };

    const persistCurrentSession = () => {
      const session = currentSession();
      if (!session) {
        return;
      }
      const server = selectedServer();
      session.serverUrl = server?.url || session.serverUrl;
      session.model = modelSelect?.value || session.model;
      session.updatedAt = nowIso();
      if (session.title === "Новый чат") {
        const firstUserMessage = session.messages.find((message) => message.role === "user");
        if (firstUserMessage) {
          session.title = chatTitleFrom(firstUserMessage.content);
        }
      }
      writeSessions();
      renderSessionList();
      renderActiveHeader();
    };

    const renderServers = () => {
      if (!serverSelect) {
        return;
      }
      const current = serverSelect.value;
      serverSelect.innerHTML = servers.map((server) => (
        `<option value="${escapeHtml(server.url)}">${escapeHtml(server.name)} - ${escapeHtml(server.url)}</option>`
      )).join("");
      if (servers.some((server) => server.url === current)) {
        serverSelect.value = current;
      }
      const session = currentSession();
      if (session?.serverUrl && servers.some((server) => server.url === session.serverUrl)) {
        serverSelect.value = session.serverUrl;
      }
      if (window.lucide) {
        window.lucide.createIcons({ nodes: ollamaChat.querySelectorAll("[data-lucide]") });
      }
      setStatus(selectedServer() ? "Готов к подключению" : "Сервер не выбран");
    };

    const renderModels = (models) => {
      if (!modelSelect) {
        return;
      }
      if (!models.length) {
        modelSelect.innerHTML = '<option value="">Модели не найдены</option>';
        return;
      }
      modelSelect.innerHTML = models.map((model) => (
        `<option value="${escapeHtml(model.name)}">${escapeHtml(model.name)}</option>`
      )).join("");
      const sessionModel = currentSession()?.model;
      if (sessionModel && models.some((model) => model.name === sessionModel)) {
        modelSelect.value = sessionModel;
      }
    };

    const appendMessage = (role, content, pending = false, save = true, createdAt = nowIso()) => {
      if (!messagesList) {
        return null;
      }
      const message = document.createElement("div");
      message.className = `ollama-message ollama-message--${role}${pending ? " ollama-message--pending" : ""}`;
      const avatar = role === "user"
        ? '<span class="ollama-message__avatar ollama-message__avatar--user" aria-hidden="true">Вы</span>'
        : '<img class="ollama-message__avatar" src="/static/img/ollama-ai-avatar.png" alt="" aria-hidden="true">';
      message.innerHTML = `
        ${avatar}
        <span class="ollama-message__bubble">
          <strong>${role === "user" ? "Вы" : "Ollama"}</strong>
          <p>${escapeHtml(content).replaceAll("\n", "<br>")}</p>
          <time>${compactDate(createdAt)}</time>
        </span>
      `;
      messagesList.appendChild(message);
      messagesList.scrollTop = messagesList.scrollHeight;
      if (save) {
        const session = currentSession();
        session.messages.push({ role, content, createdAt });
        persistCurrentSession();
      }
      return message;
    };

    const requestJson = async (url, payload) => {
      const response = await fetch(url, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || `HTTP: ${response.status}`);
      }
      return data;
    };

    const loadModels = async () => {
      const server = selectedServer();
      if (!server) {
        setStatus("Сервер не выбран", "error");
        return;
      }
      refreshModelsButton?.setAttribute("disabled", "disabled");
      setStatus("Загружаю модели...");
      try {
        const data = await requestJson("/dashboard/chat/models", { server_url: server.url });
        renderModels(data.models || []);
        persistCurrentSession();
        setStatus(`Подключено: ${server.name}`, "ok");
      } catch (error) {
        setStatus(error.message || "Ошибка подключения", "error");
        showToast({
          title: "Ollama недоступен",
          message: error.message || "Проверьте адрес сервера и запущена ли Ollama.",
          variant: "error",
          action: "",
        });
      } finally {
        refreshModelsButton?.removeAttribute("disabled");
      }
    };

    serverForm?.addEventListener("submit", (event) => {
      event.preventDefault();
      const formData = new FormData(serverForm);
      const url = String(formData.get("url") || "").trim().replace(/\/+$/, "");
      const name = String(formData.get("name") || "").trim() || "Ollama";
      if (!/^https?:\/\/[^ ]+$/i.test(url)) {
        setStatus("URL должен начинаться с http:// или https://", "error");
        return;
      }
      servers = [{ name, url }, ...servers.filter((server) => server.url !== url)];
      writeServers();
      renderServers();
      serverSelect.value = url;
      serverForm.reset();
      loadModels();
    });

    serverSelect?.addEventListener("change", () => {
      renderModels([]);
      persistCurrentSession();
      loadModels();
    });

    refreshModelsButton?.addEventListener("click", loadModels);

    modelSelect?.addEventListener("change", persistCurrentSession);

    removeServerButton?.addEventListener("click", () => {
      const server = selectedServer();
      if (!server) {
        return;
      }
      servers = servers.filter((item) => item.url !== server.url);
      if (!servers.length) {
        servers = defaultServers;
      }
      writeServers();
      renderServers();
      renderModels([]);
      loadModels();
    });

    newChatButton?.addEventListener("click", () => {
      const session = createSession();
      sessions.unshift(session);
      activeSessionId = session.id;
      writeSessions();
      renderSessionList();
      renderMessages();
      renderServers();
      loadModels();
      messageInput?.focus();
    });

    sessionList?.addEventListener("click", (event) => {
      const openButton = event.target.closest("[data-open-chat-session]");
      const deleteButton = event.target.closest("[data-delete-chat-session]");
      if (openButton) {
        activeSessionId = openButton.getAttribute("data-open-chat-session");
        writeSessions();
        renderSessionList();
        renderServers();
        renderMessages();
        loadModels();
        return;
      }
      if (deleteButton) {
        const sessionId = deleteButton.getAttribute("data-delete-chat-session");
        sessions = sessions.filter((session) => session.id !== sessionId);
        if (!sessions.length) {
          sessions = [createSession()];
        }
        if (activeSessionId === sessionId) {
          activeSessionId = sessions[0].id;
        }
        writeSessions();
        renderSessionList();
        renderMessages();
      }
    });

    clearChatButton?.addEventListener("click", () => {
      const session = currentSession();
      if (!session || !window.confirm("Очистить текущий чат?")) {
        return;
      }
      session.messages = [];
      session.title = "Новый чат";
      session.updatedAt = nowIso();
      writeSessions();
      renderSessionList();
      renderMessages();
    });

    messageInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        composeForm?.requestSubmit();
      }
    });

    composeForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const server = selectedServer();
      const model = modelSelect?.value;
      const content = messageInput?.value.trim();
      if (!server || !model || !content) {
        setStatus("Выберите сервер, модель и введите сообщение", "error");
        return;
      }

      const session = currentSession();
      session.serverUrl = server.url;
      session.model = model;
      session.messages.push({ role: "user", content, createdAt: nowIso() });
      persistCurrentSession();
      appendMessage("user", content, false, false);
      messageInput.value = "";
      const pendingMessage = appendMessage("assistant", randomThinkingText(), true, false);
      let thinkingTimer = window.setInterval(() => {
        const textNode = pendingMessage?.querySelector("p");
        if (!textNode) {
          return;
        }
        textNode.textContent = randomThinkingText(textNode.textContent);
      }, 1800);
      composeForm.querySelector("button[type='submit']")?.setAttribute("disabled", "disabled");
      setStatus("Ollama отвечает...");

      try {
        const data = await requestJson("/dashboard/chat/message", {
          server_url: server.url,
          model,
          messages: session.messages,
        });
        const answer = data.message || "Модель вернула пустой ответ.";
        session.messages.push({ role: "assistant", content: answer, createdAt: nowIso() });
        persistCurrentSession();
        window.clearInterval(thinkingTimer);
        thinkingTimer = null;
        if (pendingMessage) {
          pendingMessage.classList.remove("ollama-message--pending");
          pendingMessage.querySelector("p").innerHTML = escapeHtml(answer).replaceAll("\n", "<br>");
          pendingMessage.querySelector("time").textContent = compactDate(nowIso());
        }
        setStatus(`Ответ получен: ${model}`, "ok");
      } catch (error) {
        if (thinkingTimer) {
          window.clearInterval(thinkingTimer);
        }
        session.messages.pop();
        persistCurrentSession();
        pendingMessage?.remove();
        setStatus(error.message || "Ошибка запроса", "error");
        showToast({
          title: "Не удалось получить ответ",
          message: error.message || "Ollama не вернул ответ.",
          variant: "error",
          action: "",
        });
      } finally {
        if (thinkingTimer) {
          window.clearInterval(thinkingTimer);
        }
        composeForm.querySelector("button[type='submit']")?.removeAttribute("disabled");
        messageInput?.focus();
      }
    });

    const downloadJson = (filename, payload) => {
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    };

    exportChatButton?.addEventListener("click", () => {
      const session = currentSession();
      if (!session) {
        return;
      }
      downloadJson(`airdock-chat-${session.title.replace(/[^\p{L}\p{N}]+/gu, "-").slice(0, 36) || session.id}.json`, {
        type: "airdock-ollama-chats",
        version: 1,
        exportedAt: nowIso(),
        sessions: [session],
      });
    });

    exportAllButton?.addEventListener("click", () => {
      downloadJson("airdock-ollama-chats.json", {
        type: "airdock-ollama-chats",
        version: 1,
        exportedAt: nowIso(),
        sessions,
      });
    });

    importChatButton?.addEventListener("click", () => importFileInput?.click());

    importFileInput?.addEventListener("change", async () => {
      const file = importFileInput.files?.[0];
      if (!file) {
        return;
      }
      try {
        const payload = JSON.parse(await file.text());
        const incoming = Array.isArray(payload?.sessions) ? payload.sessions : Array.isArray(payload) ? payload : [];
        const usedIds = new Set(sessions.map((session) => session.id));
        const imported = incoming.map((session) => {
          const normalized = normalizeSession(session);
          if (usedIds.has(normalized.id)) {
            normalized.id = uid();
          }
          usedIds.add(normalized.id);
          return normalized;
        });
        if (!imported.length) {
          throw new Error("В файле нет чатов AirDock.");
        }
        sessions = [...imported, ...sessions];
        activeSessionId = imported[0].id;
        writeSessions();
        renderSessionList();
        renderServers();
        renderMessages();
        loadModels();
        showToast({
          title: "Чаты импортированы",
          message: `Добавлено: ${imported.length}`,
          variant: "success",
          action: "",
        });
      } catch (error) {
        showToast({
          title: "Не удалось импортировать",
          message: error.message || "Проверьте JSON-файл.",
          variant: "error",
          action: "",
        });
      } finally {
        importFileInput.value = "";
      }
    });

    ensureActiveSession();
    renderServers();
    renderSessionList();
    renderMessages();
    loadModels();
  }

  const mediaManager = document.querySelector("[data-media-manager]");
  if (mediaManager) {
    const uploadForm = mediaManager.querySelector("[data-media-upload-form]");
    const fileInput = mediaManager.querySelector("[data-media-file]");
    const fileTable = mediaManager.querySelector("[data-media-file-table]");
    const preview = mediaManager.querySelector("[data-media-preview]");
    const downloadLink = mediaManager.querySelector("[data-media-download]");
    const deleteButton = mediaManager.querySelector("[data-media-delete]");
    const editButton = mediaManager.querySelector("[data-media-edit]");
    const consoleOutput = mediaManager.querySelector("[data-media-console]");
    const status = mediaManager.querySelector("[data-media-status]");
    const rootLabel = mediaManager.querySelector("[data-media-root]");
    const mediaTree = mediaManager.querySelector("[data-media-tree]");
    const uploadButton = uploadForm?.querySelector('button[type="submit"]');
    const editorDialog = mediaManager.querySelector("[data-media-editor-dialog]");
    const editorTextarea = mediaManager.querySelector("[data-media-editor]");
    const editorTitle = mediaManager.querySelector("[data-media-editor-title]");
    const editorPath = mediaManager.querySelector("[data-media-editor-path]");
    let selectedEntry = null;
    let currentPath = "";
    let draggedMediaPath = "";

    const writeMediaLog = (line) => {
      if (!consoleOutput) {
        return;
      }
      const timestamp = new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      consoleOutput.textContent = `${consoleOutput.textContent}\n[${timestamp}] ${line}`.trim();
      consoleOutput.scrollTop = consoleOutput.scrollHeight;
    };

    const setMediaStatus = (text) => {
      if (status) {
        status.innerHTML = `<i></i>${escapeHtml(text)}`;
      }
    };

    const formatBytes = (bytes) => {
      const value = Number(bytes || 0);
      if (value < 1024) {
        return `${value} B`;
      }
      if (value < 1024 * 1024) {
        return `${(value / 1024).toFixed(1)} KB`;
      }
      if (value < 1024 * 1024 * 1024) {
        return `${(value / 1024 / 1024).toFixed(1)} MB`;
      }
      return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`;
    };

    const fileExtension = (name) => String(name || "").split(".").pop()?.toLowerCase() || "";

    const fileKind = (name) => {
      const ext = fileExtension(name);
      if (["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext)) {
        return "image";
      }
      if (["mp4", "webm", "mov", "mkv"].includes(ext)) {
        return "video";
      }
      if (["mp3", "wav", "ogg", "flac"].includes(ext)) {
        return "audio";
      }
      if (["zip", "tar", "gz", "rar", "7z"].includes(ext)) {
        return "archive";
      }
      return ext || "file";
    };

    const fileIcon = (kind) => {
      if (kind === "image") return "image";
      if (kind === "video") return "film";
      if (kind === "audio") return "music";
      if (kind === "archive") return "archive";
      return "file";
    };

    const isImageFile = (name) => ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico"].includes(fileExtension(name));

    const renderBreadcrumb = () => {
      const breadcrumb = mediaManager.querySelector("[data-media-breadcrumb]");
      if (!breadcrumb) {
        return;
      }
      const parts = currentPath.split("/").filter(Boolean);
      let accumulated = "";
      breadcrumb.innerHTML = [
        '<button type="button" data-media-breadcrumb-path="">media</button>',
        ...parts.map((part) => {
          accumulated = accumulated ? `${accumulated}/${part}` : part;
          return `<button type="button" data-media-breadcrumb-path="${escapeHtml(accumulated)}">${escapeHtml(part)}</button>`;
        }),
      ].join("");
    };

    const renderPreview = (file) => {
      selectedEntry = file;
      if (!preview || !downloadLink || !deleteButton) {
        return;
      }
      if (!file) {
        preview.innerHTML = `
          <i data-lucide="file-search" aria-hidden="true"></i>
          <strong>Выберите файл</strong>
          <p>Здесь появятся размер, ссылка скачивания и быстрые действия.</p>
        `;
        downloadLink.href = "#";
        downloadLink.classList.add("is-disabled");
        deleteButton.disabled = true;
        if (editButton) {
          editButton.disabled = true;
          editButton.hidden = true;
        }
        if (window.lucide) {
          window.lucide.createIcons({ nodes: preview.querySelectorAll("[data-lucide]") });
        }
        return;
      }
      const isFolder = file.type === "folder";
      const kind = isFolder ? "folder" : fileKind(file.name);
      const isImage = kind === "image" && !file.name.toLowerCase().endsWith(".svg");
      preview.innerHTML = `
        ${isImage ? `<img class="media-preview-image" src="${escapeHtml(file.download_url)}" alt="">` : `<i data-lucide="${isFolder ? "folder" : fileIcon(kind)}" aria-hidden="true"></i>`}
        <strong>${escapeHtml(file.name)}</strong>
        <p>${isFolder ? "Папка" : `${escapeHtml(formatBytes(file.size))} · ${escapeHtml(kind)}`}</p>
        <code>media/${escapeHtml(file.path || file.name)}</code>
      `;
      downloadLink.href = isFolder ? "#" : file.download_url;
      downloadLink.classList.toggle("is-disabled", isFolder);
      deleteButton.disabled = false;
      if (editButton) {
        const canEdit = !isFolder && !isImageFile(file.name) && isEditableFile(file.name);
        editButton.disabled = !canEdit;
        editButton.hidden = !canEdit;
      }
      if (window.lucide) {
        window.lucide.createIcons({ nodes: preview.querySelectorAll("[data-lucide]") });
      }
    };

    const isEditableFile = (name) => {
      const ext = String(name || "").split(".").pop()?.toLowerCase();
      if (isImageFile(name)) {
        return false;
      }
      return [
        "txt", "md", "json", "yaml", "yml", "toml", "ini", "env", "conf", "cfg", "log",
        "py", "js", "ts", "css", "html", "xml", "sh", "bat", "ps1", "sql",
      ].includes(ext) || String(name || "").startsWith(".");
    };

    const renderFiles = (entries) => {
      if (!fileTable) {
        return;
      }
      const head = `
        <div class="sftp-file-row sftp-file-row--head">
          <span>Имя</span>
          <span>Размер</span>
          <span>Тип</span>
          <span>Изменен</span>
        </div>
      `;
      if (!entries.length) {
        fileTable.innerHTML = `${head}
          <div class="sftp-file-row media-file-empty">
            <span><i data-lucide="folder-open" aria-hidden="true"></i>Эта папка пуста</span>
            <span></span><span></span><span></span>
          </div>
        `;
      } else {
        fileTable.innerHTML = head + entries.map((file) => {
          const isFolder = file.type === "folder";
          const kind = isFolder ? "folder" : fileKind(file.name);
          return `
            <button class="sftp-file-row ${isFolder ? "sftp-file-row--folder" : ""}" type="button" draggable="true" data-media-entry-type="${escapeHtml(file.type)}" data-media-entry-path="${escapeHtml(file.path)}">
              <span><i data-lucide="${isFolder ? "folder" : fileIcon(kind)}" aria-hidden="true"></i>${escapeHtml(file.name)}</span>
              <span>${isFolder ? "--" : escapeHtml(formatBytes(file.size))}</span>
              <span>${escapeHtml(kind)}</span>
              <span>${new Date(Number(file.modified_at) * 1000).toLocaleString("ru-RU")}</span>
            </button>
          `;
        }).join("");
      }
      fileTable.dataset.files = JSON.stringify(entries);
      if (window.lucide) {
        window.lucide.createIcons({ nodes: fileTable.querySelectorAll("[data-lucide]") });
      }
    };

    const renderTree = (entries) => {
      if (!mediaTree) {
        return;
      }
      const parentPath = currentPath.split("/").filter(Boolean).slice(0, -1).join("/");
      const currentLabel = currentPath ? `media/${currentPath}` : "media/";
      mediaTree.innerHTML = `
        <button type="button" class="is-active" data-media-drop-folder="true" data-media-tree-path="${escapeHtml(currentPath)}">
          <i data-lucide="folder-open" aria-hidden="true"></i>${escapeHtml(currentLabel)}
        </button>
        ${currentPath ? `
          <button type="button" data-media-drop-folder="true" data-media-tree-path="${escapeHtml(parentPath)}">
            <i data-lucide="corner-up-left" aria-hidden="true"></i>..
          </button>
        ` : ""}
        ${entries.map((entry) => `
          <button type="button" class="${entry.path === selectedEntry?.path ? "is-selected" : ""}" ${entry.type === "folder" ? 'data-media-drop-folder="true"' : ""} data-media-tree-${entry.type === "folder" ? "path" : "file"}="${escapeHtml(entry.path)}">
            <i data-lucide="${entry.type === "folder" ? "folder" : fileIcon(fileKind(entry.name))}" aria-hidden="true"></i>${escapeHtml(entry.name)}
          </button>
        `).join("")}
      `;
      if (window.lucide) {
        window.lucide.createIcons({ nodes: mediaTree.querySelectorAll("[data-lucide]") });
      }
    };

    const loadMediaFiles = async () => {
      try {
        setMediaStatus("Обновляю media/");
        const response = await fetch(`/dashboard/files/media/list?path=${encodeURIComponent(currentPath)}`, { headers: { Accept: "application/json" }, cache: "no-store" });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || `HTTP: ${response.status}`);
        }
        currentPath = payload.path || "";
        renderBreadcrumb();
        if (rootLabel) {
          rootLabel.textContent = currentPath ? `media/${currentPath}` : (payload.root || "media/");
        }
        const entries = payload.entries || payload.files || [];
        renderFiles(entries);
        renderTree(entries);
        renderPreview(null);
        setMediaStatus(`${entries.length} объектов`);
        writeMediaLog(`list media/${currentPath} (${entries.length})`);
      } catch (error) {
        setMediaStatus("Ошибка чтения");
        writeMediaLog(`error: ${error.message || "media list failed"}`);
      }
    };

    const uploadFiles = async (files) => {
      const fileList = Array.from(files || []);
      if (!fileList.length) {
        return;
      }
      setMediaStatus(`Загружаю: ${fileList.length}`);
      for (const file of fileList) {
        const formData = new FormData();
        formData.append("path", currentPath);
        formData.append("file", file);
        try {
          const response = await fetch("/dashboard/files/media/upload", {
            method: "POST",
            headers: { Accept: "application/json" },
            body: formData,
          });
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(payload.detail || `HTTP: ${response.status}`);
          }
          writeMediaLog(`upload media/${payload.path || payload.name}`);
        } catch (error) {
          writeMediaLog(`upload ${file.name} error: ${error.message || "failed"}`);
        }
      }
      uploadForm?.reset();
      await loadMediaFiles();
    };

    const uploadSelectedFile = async () => {
      const files = fileInput?.files;
      if (!files?.length) {
        fileInput?.click();
        return;
      }
      await uploadFiles(files);
    };

    const openEditor = async () => {
      if (!selectedEntry || selectedEntry.type === "folder" || !isEditableFile(selectedEntry.name)) {
        return;
      }
      const formData = new FormData();
      try {
        setMediaStatus("Открываю редактор");
        const response = await fetch(`/dashboard/files/media/content?path=${encodeURIComponent(selectedEntry.path)}`, {
          headers: { Accept: "application/json" },
          cache: "no-store",
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || `HTTP: ${response.status}`);
        }
        if (editorTitle) {
          editorTitle.textContent = selectedEntry.name;
        }
        if (editorPath) {
          editorPath.textContent = `media/${selectedEntry.path}`;
        }
        if (editorTextarea) {
          editorTextarea.value = payload.content || "";
        }
        if (window.lucide) {
          window.lucide.createIcons({ nodes: editorDialog.querySelectorAll("[data-lucide]") });
        }
        editorDialog?.showModal();
        editorTextarea?.focus();
        writeMediaLog(`edit media/${selectedEntry.path}`);
      } catch (error) {
        setMediaStatus("Редактор недоступен");
        writeMediaLog(`edit error: ${error.message || "failed"}`);
      }
    };

    uploadForm?.addEventListener("submit", (event) => {
      event.preventDefault();
      uploadSelectedFile();
    });

    uploadButton?.addEventListener("click", (event) => {
      if (!fileInput?.files?.length) {
        event.preventDefault();
        fileInput?.click();
      }
    });

    fileInput?.addEventListener("change", () => {
      if (fileInput.files?.length) {
        uploadSelectedFile();
      }
    });

    const hasDraggedFiles = (event) => Array.from(event.dataTransfer?.types || []).includes("Files");

    mediaManager.addEventListener("dragenter", (event) => {
      if (!hasDraggedFiles(event)) {
        return;
      }
      event.preventDefault();
      mediaManager.classList.add("media-page--dragging");
    });

    mediaManager.addEventListener("dragover", (event) => {
      if (!hasDraggedFiles(event)) {
        return;
      }
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      mediaManager.classList.add("media-page--dragging");
    });

    mediaManager.addEventListener("dragleave", (event) => {
      if (!mediaManager.contains(event.relatedTarget)) {
        mediaManager.classList.remove("media-page--dragging");
      }
    });

    mediaManager.addEventListener("drop", async (event) => {
      event.preventDefault();
      mediaManager.classList.remove("media-page--dragging");
      if (!event.dataTransfer?.files?.length) {
        return;
      }
      await uploadFiles(event.dataTransfer.files);
    });

    fileTable?.addEventListener("click", (event) => {
      const row = event.target.closest("[data-media-entry-path]");
      if (!row) {
        return;
      }
      const files = JSON.parse(fileTable.dataset.files || "[]");
      const file = files.find((item) => item.path === row.getAttribute("data-media-entry-path"));
      if (!file) {
        return;
      }
      fileTable.querySelectorAll(".sftp-file-row.is-selected").forEach((item) => item.classList.remove("is-selected"));
      row.classList.add("is-selected");
      renderPreview(file);
      renderTree(JSON.parse(fileTable.dataset.files || "[]"));
      writeMediaLog(`select media/${file.path}`);
    });

    mediaTree?.addEventListener("click", async (event) => {
      const folderButton = event.target.closest("[data-media-tree-path]");
      const fileButton = event.target.closest("[data-media-tree-file]");
      if (folderButton) {
        currentPath = folderButton.getAttribute("data-media-tree-path") || "";
        await loadMediaFiles();
        return;
      }
      if (fileButton) {
        const entries = JSON.parse(fileTable?.dataset.files || "[]");
        const entry = entries.find((item) => item.path === fileButton.getAttribute("data-media-tree-file"));
        if (!entry) {
          return;
        }
        renderPreview(entry);
        renderTree(entries);
        writeMediaLog(`select media/${entry.path}`);
      }
    });

    fileTable?.addEventListener("dblclick", async (event) => {
      const row = event.target.closest("[data-media-entry-path]");
      if (!row) {
        return;
      }
      const entries = JSON.parse(fileTable.dataset.files || "[]");
      const entry = entries.find((item) => item.path === row.getAttribute("data-media-entry-path"));
      if (entry?.type !== "folder") {
        return;
      }
      currentPath = entry.path;
      await loadMediaFiles();
    });

    const moveEntry = async (source, targetDir) => {
      if (!source || source === targetDir) {
        return;
      }
      try {
        const response = await fetch("/dashboard/files/media/move", {
          method: "POST",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({ source, target_dir: targetDir }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || `HTTP: ${response.status}`);
        }
        writeMediaLog(`move media/${source} -> media/${targetDir || ""}`);
        await loadMediaFiles();
      } catch (error) {
        writeMediaLog(`move error: ${error.message || "failed"}`);
      }
    };

    fileTable?.addEventListener("dragstart", (event) => {
      const row = event.target.closest("[data-media-entry-path]");
      if (!row) {
        return;
      }
      draggedMediaPath = row.getAttribute("data-media-entry-path") || "";
      event.dataTransfer.setData("text/plain", draggedMediaPath);
      event.dataTransfer.effectAllowed = "move";
      row.classList.add("is-dragging");
    });

    fileTable?.addEventListener("dragend", () => {
      draggedMediaPath = "";
      fileTable.querySelectorAll(".is-dragging, .is-drop-target").forEach((row) => row.classList.remove("is-dragging", "is-drop-target"));
      mediaTree?.querySelectorAll(".is-drop-target").forEach((row) => row.classList.remove("is-drop-target"));
    });

    mediaManager.addEventListener("dragover", (event) => {
      const sourcePath = draggedMediaPath;
      const folderTarget = event.target.closest('[data-media-entry-type="folder"], [data-media-drop-folder], [data-media-breadcrumb-path], [data-media-up]');
      if (!sourcePath || !folderTarget) {
        return;
      }
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      folderTarget.classList.add("is-drop-target");
    });

    mediaManager.addEventListener("dragleave", (event) => {
      const target = event.target.closest?.(".is-drop-target");
      if (target && !target.contains(event.relatedTarget)) {
        target.classList.remove("is-drop-target");
      }
    });

    mediaManager.addEventListener("drop", async (event) => {
      const sourcePath = draggedMediaPath;
      const folderTarget = event.target.closest('[data-media-entry-type="folder"], [data-media-drop-folder], [data-media-breadcrumb-path], [data-media-up]');
      if (!sourcePath || !folderTarget) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const parentPath = currentPath.split("/").filter(Boolean).slice(0, -1).join("/");
      const targetDir = folderTarget.hasAttribute("data-media-up")
        ? parentPath
        : folderTarget.getAttribute("data-media-entry-path") || folderTarget.getAttribute("data-media-tree-path") || folderTarget.getAttribute("data-media-breadcrumb-path") || "";
      await moveEntry(sourcePath, targetDir);
    });

    mediaManager.querySelector("[data-media-refresh]")?.addEventListener("click", loadMediaFiles);

    mediaManager.querySelector("[data-media-up]")?.addEventListener("click", async () => {
      const parts = currentPath.split("/").filter(Boolean);
      parts.pop();
      currentPath = parts.join("/");
      await loadMediaFiles();
    });

    mediaManager.querySelector("[data-media-new-folder]")?.addEventListener("click", async () => {
      const name = window.prompt("Название новой папки");
      if (!name) {
        return;
      }
      try {
        const response = await fetch("/dashboard/files/media/folder", {
          method: "POST",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({ path: currentPath, name }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || `HTTP: ${response.status}`);
        }
        writeMediaLog(`mkdir media/${payload.path}`);
        await loadMediaFiles();
      } catch (error) {
        writeMediaLog(`mkdir error: ${error.message || "failed"}`);
      }
    });

    mediaManager.querySelector("[data-media-breadcrumb]")?.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-media-breadcrumb-path]");
      if (!button) {
        return;
      }
      currentPath = button.getAttribute("data-media-breadcrumb-path") || "";
      await loadMediaFiles();
    });

    deleteButton?.addEventListener("click", async () => {
      if (!selectedEntry || !window.confirm(`Удалить ${selectedEntry.name}?`)) {
        return;
      }
      try {
        const response = await fetch("/dashboard/files/media/delete", {
          method: "POST",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({ path: selectedEntry.path }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || `HTTP: ${response.status}`);
        }
        writeMediaLog(`delete media/${selectedEntry.path}`);
        await loadMediaFiles();
      } catch (error) {
        writeMediaLog(`delete error: ${error.message || "failed"}`);
      }
    });

    editButton?.addEventListener("click", openEditor);

    mediaManager.querySelectorAll("[data-media-editor-close]").forEach((button) => {
      button.addEventListener("click", () => editorDialog?.close());
    });

    editorDialog?.addEventListener("click", (event) => {
      if (event.target === editorDialog) {
        editorDialog.close();
      }
    });

    mediaManager.querySelector("[data-media-save-editor]")?.addEventListener("click", async () => {
      if (!selectedEntry || !editorTextarea) {
        return;
      }
      try {
        const response = await fetch("/dashboard/files/media/content", {
          method: "POST",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({ path: selectedEntry.path, content: editorTextarea.value || "" }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || `HTTP: ${response.status}`);
        }
        writeMediaLog(`save media/${selectedEntry.path}`);
        editorDialog?.close();
        await loadMediaFiles();
      } catch (error) {
        writeMediaLog(`save error: ${error.message || "failed"}`);
      }
    });

    loadMediaFiles();
  }
});
