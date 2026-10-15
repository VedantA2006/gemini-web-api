/**
 * Gemini Web Studio — Interactive Client Logic
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const statusServerDot = document.getElementById("status-server-dot");
  const statusServerText = document.getElementById("status-server-text");
  const statusSessionDot = document.getElementById("status-session-dot");
  const statusSessionText = document.getElementById("status-session-text");
  const statusModelText = document.getElementById("status-model-text");
  const hintModelName = document.getElementById("hint-model-name");

  const selectModel = document.getElementById("select-model");
  const inputSystemPrompt = document.getElementById("input-system-prompt");
  const toggleStream = document.getElementById("toggle-stream");
  const toggleMockMode = document.getElementById("toggle-mock-mode");
  const btnNewChat = document.getElementById("btn-new-chat");

  const chatMessages = document.getElementById("chat-messages");
  const welcomeHero = document.getElementById("welcome-hero");
  const sessionBanner = document.getElementById("session-banner");
  const sessionBannerText = document.getElementById("session-banner-text");

  const inputPrompt = document.getElementById("input-prompt");
  const btnSend = document.getElementById("btn-send-prompt");
  const btnStop = document.getElementById("btn-stop-generation");

  // Modals
  const modalSettings = document.getElementById("modal-settings");
  const btnOpenSettings = document.getElementById("btn-open-settings");
  const btnCloseSettings = document.getElementById("btn-close-settings");
  const btnCancelSettings = document.getElementById("btn-cancel-settings");
  const btnSaveSettings = document.getElementById("btn-save-settings");
  const settingBaseUrl = document.getElementById("setting-base-url");
  const settingApiKey = document.getElementById("setting-api-key");

  const modalLoginGuide = document.getElementById("modal-login-guide");
  const btnHeaderLogin = document.getElementById("btn-header-login");
  const btnBannerLogin = document.getElementById("btn-banner-login");
  const btnCloseLoginGuide = document.getElementById("btn-close-login-guide");
  const btnDismissLoginGuide = document.getElementById("btn-dismiss-login-guide");
  const btnTriggerBrowserLogin = document.getElementById("btn-trigger-browser-login");
  const loginLauncherStatus = document.getElementById("login-launcher-status");

  // State
  let conversationHistory = [];
  let isGenerating = false;
  let activeAbortController = null;
  let serverAuthenticated = false;

  // Retrieve saved settings
  let localApiKey = localStorage.getItem("gemini_web_api_key") || "";
  let localBaseUrl = localStorage.getItem("gemini_web_base_url") || "/v1";

  settingApiKey.value = localApiKey;
  settingBaseUrl.value = localBaseUrl;

  // --- Initial Configuration & Health Check ---

  async function checkServerStatus() {
    try {
      const res = await fetch("/health");
      if (!res.ok) throw new Error("Health check non-200");
      const data = await res.json();

      statusServerDot.className = "status-dot online";
      statusServerText.textContent = "API Online";

      serverAuthenticated = data.authenticated;
      if (serverAuthenticated) {
        statusSessionDot.className = "status-dot online";
        statusSessionText.textContent = "Session: Connected";
        sessionBanner.className = "session-alert-banner authenticated";
        sessionBannerText.textContent = "🟢 Gemini Web session is connected and authenticated.";
        if (btnBannerLogin) btnBannerLogin.style.display = "none";
      } else {
        statusSessionDot.className = "status-dot warning";
        statusSessionText.textContent = "Session: Not Logged In";
        sessionBanner.className = "session-alert-banner";
        sessionBannerText.textContent = "⚠️ Gemini Web session not yet authenticated. Click 'Browser Login' or enable 'Test Mode' to test.";
        if (btnBannerLogin) btnBannerLogin.style.display = "inline-flex";
      }
    } catch (err) {
      statusServerDot.className = "status-dot error";
      statusServerText.textContent = "API Offline";
      statusSessionDot.className = "status-dot error";
      statusSessionText.textContent = "Session: Unavailable";
    }
  }

  // Attempt to auto-fetch local config if available
  async function fetchLocalConfig() {
    try {
      const res = await fetch("/api/client-config");
      if (res.ok) {
        const data = await res.json();
        if (data.api_key && !localApiKey) {
          localApiKey = data.api_key;
          localStorage.setItem("gemini_web_api_key", localApiKey);
          settingApiKey.value = localApiKey;
        }
      }
    } catch (e) {
      /* ignore */
    }
  }

  fetchLocalConfig();
  checkServerStatus();
  setInterval(checkServerStatus, 5000);

  // --- Model Selection Sync ---

  selectModel.addEventListener("change", () => {
    statusModelText.textContent = selectModel.value;
    hintModelName.textContent = selectModel.value;
  });

  // --- Modal Event Listeners ---

  btnOpenSettings.addEventListener("click", () => modalSettings.classList.add("active"));
  btnCloseSettings.addEventListener("click", () => modalSettings.classList.remove("active"));
  btnCancelSettings.addEventListener("click", () => modalSettings.classList.remove("active"));

  btnSaveSettings.addEventListener("click", () => {
    localApiKey = settingApiKey.value.trim();
    localBaseUrl = settingBaseUrl.value.trim() || "/v1";
    localStorage.setItem("gemini_web_api_key", localApiKey);
    localStorage.setItem("gemini_web_base_url", localBaseUrl);
    modalSettings.classList.remove("active");
  });

  function openLoginModal() {
    modalLoginGuide.classList.add("active");
    loginLauncherStatus.textContent = "";
  }

  btnHeaderLogin.addEventListener("click", openLoginModal);
  if (btnBannerLogin) btnBannerLogin.addEventListener("click", openLoginModal);
  btnCloseLoginGuide.addEventListener("click", () => modalLoginGuide.classList.remove("active"));
  btnDismissLoginGuide.addEventListener("click", () => modalLoginGuide.classList.remove("active"));

  // Tabs in Login Modal
  const tabBtnCookie = document.getElementById("tab-btn-cookie");
  const tabBtnConsole = document.getElementById("tab-btn-console");
  const tabContentCookie = document.getElementById("tab-content-cookie");
  const tabContentConsole = document.getElementById("tab-content-console");
  const inputCookiePaste = document.getElementById("input-cookie-paste");
  const btnSubmitCookieImport = document.getElementById("btn-submit-cookie-import");
  const cookieImportFeedback = document.getElementById("cookie-import-feedback");

  if (tabBtnCookie && tabBtnConsole) {
    tabBtnCookie.addEventListener("click", () => {
      tabBtnCookie.className = "btn-pill btn-primary";
      tabBtnConsole.className = "btn-pill btn-secondary";
      tabContentCookie.style.display = "block";
      tabContentConsole.style.display = "none";
    });

    tabBtnConsole.addEventListener("click", () => {
      tabBtnCookie.className = "btn-pill btn-secondary";
      tabBtnConsole.className = "btn-pill btn-primary";
      tabContentCookie.style.display = "none";
      tabContentConsole.style.display = "block";
    });
  }

  if (btnSubmitCookieImport) {
    btnSubmitCookieImport.addEventListener("click", async () => {
      let rawCookie = inputCookiePaste.value.trim();
      if (!rawCookie) {
        cookieImportFeedback.innerHTML = "<span style='color: #f87171;'>Please paste a cookie value or string.</span>";
        return;
      }

      // If user pasted bare cookie value without name, default to __Secure-1PSID
      if (!rawCookie.includes("=") && !rawCookie.startsWith("[")) {
        rawCookie = `__Secure-1PSID=${rawCookie}`;
      }

      cookieImportFeedback.innerHTML = "<span style='color: #38bdf8;'>Importing and verifying cookies...</span>";

      try {
        const res = await fetch("/api/import-cookies", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cookie: rawCookie }),
        });
        const data = await res.json();

        if (data.status === "ok" && data.authenticated) {
          cookieImportFeedback.innerHTML = `<span style='color: #34d399;'>✅ Success! ${data.cookies_count} cookie(s) saved and verified. Active now!</span>`;
          checkServerStatus();
          setTimeout(() => {
            modalLoginGuide.classList.remove("active");
          }, 1500);
        } else {
          cookieImportFeedback.innerHTML = `<span style='color: #fbbf24;'>⚠️ ${data.message || 'Saved, but no recognized Google tokens found. Please check __Secure-1PSID.'}</span>`;
          checkServerStatus();
        }
      } catch (err) {
        cookieImportFeedback.innerHTML = `<span style='color: #f87171;'>Error saving cookies: ${err.message}</span>`;
      }
    });
  }

  btnTriggerBrowserLogin.addEventListener("click", async () => {
    loginLauncherStatus.textContent = "⏳ Launching Chromium login window...";
    try {
      const res = await fetch("/api/launch-login", { method: "POST" });
      const data = await res.json();
      if (data.status === "ok") {
        loginLauncherStatus.textContent = "✅ Chromium browser window opened! Please sign into your Google account in that window.";
      } else {
        loginLauncherStatus.textContent = `Note: ${data.message || 'Please run python scripts/setup_browser.py in terminal'}`;
      }
    } catch (e) {
      loginLauncherStatus.textContent = "Please run `python scripts/setup_browser.py` in your terminal to authenticate.";
    }
  });

  // --- Auto-resize Textarea ---

  inputPrompt.addEventListener("input", () => {
    inputPrompt.style.height = "auto";
    inputPrompt.style.height = Math.min(inputPrompt.scrollHeight, 180) + "px";
  });

  inputPrompt.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendPrompt();
    }
  });

  btnSend.addEventListener("click", handleSendPrompt);

  // Stop Generation
  btnStop.addEventListener("click", () => {
    if (activeAbortController) {
      activeAbortController.abort();
      activeAbortController = null;
    }
    finishGeneration();
  });

  // Reset Chat
  btnNewChat.addEventListener("click", () => {
    conversationHistory = [];
    chatMessages.innerHTML = "";
    if (welcomeHero) chatMessages.appendChild(welcomeHero);
  });

  // Starter Buttons
  document.querySelectorAll(".starter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prompt = btn.getAttribute("data-prompt");
      if (prompt) {
        inputPrompt.value = prompt;
        inputPrompt.style.height = "auto";
        handleSendPrompt();
      }
    });
  });

  // --- Send Message & Stream Handling ---

  async function handleSendPrompt() {
    const text = inputPrompt.value.trim();
    if (!text || isGenerating) return;

    // Remove welcome hero once first prompt is sent
    if (welcomeHero && welcomeHero.parentNode === chatMessages) {
      chatMessages.removeChild(welcomeHero);
    }

    // Append User Message to UI
    appendMessage("user", text);
    inputPrompt.value = "";
    inputPrompt.style.height = "auto";

    // Prepare assistant bubble
    const assistantBubble = appendMessage("assistant", "");
    const contentContainer = assistantBubble.querySelector(".bubble-content");
    const cursor = document.createElement("span");
    cursor.className = "streaming-cursor";
    contentContainer.appendChild(cursor);

    setGeneratingState(true);

    // Build payload messages
    const requestMessages = [];
    const systemPrompt = inputSystemPrompt.value.trim();
    if (systemPrompt) {
      requestMessages.push({ role: "system", content: systemPrompt });
    }

    conversationHistory.forEach((m) => requestMessages.push(m));
    requestMessages.push({ role: "user", content: text });

    const isStreaming = toggleStream.checked;
    const isMockMode = toggleMockMode.checked;
    const selectedModel = selectModel.value;

    activeAbortController = new AbortController();

    const headers = {
      "Content-Type": "application/json",
    };
    if (localApiKey) {
      headers["Authorization"] = `Bearer ${localApiKey}`;
    }
    if (isMockMode) {
      headers["X-Mock-Mode"] = "true";
    }

    const payload = {
      model: selectedModel,
      messages: requestMessages,
      stream: isStreaming,
    };

    let accumulatedText = "";

    try {
      const response = await fetch(`${localBaseUrl}/chat/completions`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        signal: activeAbortController.signal,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = errorData.error?.message || `HTTP ${response.status} Error`;
        const errorCode = errorData.error?.code || "";

        contentContainer.removeChild(cursor);
        renderError(contentContainer, errorMsg, errorCode);
        finishGeneration();
        return;
      }

      if (isStreaming) {
        // Read SSE Stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop(); // keep partial trailing line

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed === "data: [DONE]") continue;

            if (trimmed.startsWith("data: ")) {
              try {
                const chunkData = JSON.parse(trimmed.slice(6));
                const deltaContent = chunkData.choices?.[0]?.delta?.content;
                if (deltaContent) {
                  accumulatedText += deltaContent;
                  // Update text in UI
                  renderContent(contentContainer, accumulatedText, cursor);
                  chatMessages.scrollTop = chatMessages.scrollHeight;
                }
              } catch (e) {
                /* skip partial json */
              }
            }
          }
        }
      } else {
        // Non-streaming response
        const data = await response.json();
        accumulatedText = data.choices?.[0]?.message?.content || "";
        renderContent(contentContainer, accumulatedText, null);
      }

      // Generation successful
      if (cursor.parentNode) cursor.remove();
      conversationHistory.push({ role: "user", content: text });
      conversationHistory.push({ role: "assistant", content: accumulatedText });

    } catch (err) {
      if (err.name === "AbortError") {
        if (cursor.parentNode) cursor.remove();
        if (!accumulatedText) {
          contentContainer.textContent = "(Generation stopped by user)";
        }
      } else {
        if (cursor.parentNode) cursor.remove();
        renderError(contentContainer, `Connection failed: ${err.message}`, "network_error");
      }
    } finally {
      finishGeneration();
    }
  }

  function setGeneratingState(generating) {
    isGenerating = generating;
    btnSend.disabled = generating;
    if (generating) {
      btnStop.classList.add("active");
    } else {
      btnStop.classList.remove("active");
    }
  }

  function finishGeneration() {
    setGeneratingState(false);
    activeAbortController = null;
  }

  // --- Message Bubble DOM Rendering ---

  function appendMessage(role, text) {
    const row = document.createElement("div");
    row.className = `message-row ${role}`;

    const avatar = document.createElement("div");
    avatar.className = `avatar ${role}-avatar`;
    avatar.textContent = role === "user" ? "U" : "✦";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    const contentDiv = document.createElement("div");
    contentDiv.className = "bubble-content";
    contentDiv.textContent = text;
    bubble.appendChild(contentDiv);

    if (role === "assistant") {
      const footer = document.createElement("div");
      footer.className = "message-footer";
      footer.innerHTML = `
        <span>Gemini Web</span>
        <button class="btn-copy">📋 Copy</button>
      `;
      const copyBtn = footer.querySelector(".btn-copy");
      copyBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(contentDiv.innerText);
        copyBtn.textContent = "✓ Copied!";
        setTimeout(() => (copyBtn.innerHTML = "📋 Copy"), 2000);
      });
      bubble.appendChild(footer);
    }

    row.appendChild(avatar);
    row.appendChild(bubble);
    chatMessages.appendChild(row);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    return bubble;
  }

  function renderContent(container, markdownText, cursorElement) {
    // Basic Markdown formatting for code blocks, bold, lists
    let formatted = escapeHtml(markdownText)
      // Code blocks with syntax formatting
      .replace(/```([a-zA-Z0-9]*)\n([\s\S]*?)```/g, (match, lang, code) => {
        return `<pre><code>${code}</code></pre>`;
      })
      // Inline code
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      // Bold text
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      // Line breaks
      .replace(/\n\n/g, '</p><p>')
      .replace(/\n/g, '<br>');

    container.innerHTML = `<p>${formatted}</p>`;
    if (cursorElement) {
      container.appendChild(cursorElement);
    }
  }

  function renderError(container, message, code) {
    container.innerHTML = `
      <div style="color: #f87171; line-height: 1.4;">
        <strong>⚠️ Request Error (${escapeHtml(code)})</strong>
        <p style="margin-top: 6px; font-size: 0.9em;">${escapeHtml(message)}</p>
      </div>
    `;
    if (code === "session_expired") {
      const loginBtn = document.createElement("button");
      loginBtn.className = "btn-pill btn-primary";
      loginBtn.style.marginTop = "10px";
      loginBtn.style.fontSize = "0.8rem";
      loginBtn.style.padding = "4px 12px";
      loginBtn.textContent = "Open Browser Login";
      loginBtn.onclick = openLoginModal;
      container.appendChild(loginBtn);
    }
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
  }
});
