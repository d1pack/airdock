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
            </div>
            <div class="docker-container-card__actions">
              <button class="container-action container-action--logs" type="button" title="Показать логи" data-container-logs data-node-id="${escapeHtml(container.node_id)}" data-container-id="${escapeHtml(container.id)}" data-container-name="${escapeHtml(container.name)}" data-node-name="${escapeHtml(container.node_name)}">
                <i data-lucide="square-terminal" aria-hidden="true"></i>
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
          title: action === "stop" ? "Контейнер остановлен" : "Контейнер удален",
          message: containerId,
          variant: "success",
          action: "",
        });
        await updateProjectMetrics();
      } catch (error) {
        showToast({
          title: action === "stop" ? "Не удалось остановить контейнер" : "Не удалось удалить контейнер",
          message: error.message || "Docker вернул ошибку.",
          href: "/docs/docker-access",
        });
        button.disabled = false;
      }
    };

    containersRail?.addEventListener("click", (event) => {
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
});
