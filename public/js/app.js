// Main Switcher Application Controller

class SwitcherApp {
  constructor() {
    this.ws = null;
    this.wsReconnectTimer = null;
    this.currentState = null;
    this.currentConfig = null;
    this.sourceSearchFilter = '';
    this.soundEnabled = true;
    this.showThumbnails = localStorage.getItem('vmix_show_thumbnails') === 'true';
    this.audioCtx = null;
    this.pingTimer = null;

    // Cache DOM Elements
    this.dom = {
      loginModal: document.getElementById('login-modal'),
      loginForm: document.getElementById('login-form'),
      loginPassword: document.getElementById('login-password'),
      loginError: document.getElementById('login-error'),
      loginBtn: document.getElementById('login-btn'),

      appContainer: document.getElementById('app-container'),
      vmixStatusBadge: document.getElementById('vmix-status-badge'),
      vmixStatusText: document.getElementById('vmix-status-text'),
      recBadge: document.getElementById('rec-badge'),
      streamBadge: document.getElementById('stream-badge'),
      fullscreenBadge: document.getElementById('fullscreen-badge'),

      soundToggleBtn: document.getElementById('sound-toggle-btn'),
      soundIconOn: document.getElementById('sound-icon-on'),
      soundIconOff: document.getElementById('sound-icon-off'),
      thumbToggleBtn: document.getElementById('thumb-toggle-btn'),

      pgmNumber: document.getElementById('pgm-number'),
      pgmName: document.getElementById('pgm-name'),
      prvNumber: document.getElementById('prv-number'),
      prvName: document.getElementById('prv-name'),

      btnCut: document.getElementById('btn-cut'),
      btnAuto: document.getElementById('btn-auto'),
      btnAutoLabel: document.getElementById('btn-auto-label'),
      btnFtb: document.getElementById('btn-ftb'),
      btnQuickplay: document.getElementById('btn-quickplay'),
      quickTransitionSelect: document.getElementById('quick-transition-select'),

      sourcesGrid: document.getElementById('sources-grid'),
      ignoredCountBadge: document.getElementById('ignored-count-badge'),
      sourceFilterStatus: document.getElementById('source-filter-status'),
      currentModeBadge: document.getElementById('current-mode-badge'),
      currentModeDesc: document.getElementById('current-mode-desc'),

      manageSourcesBtn: document.getElementById('manage-sources-btn'),
      manageSourcesModal: document.getElementById('manage-sources-modal'),
      closeManageSourcesBtn: document.getElementById('close-manage-sources-btn'),
      doneManageSourcesBtn: document.getElementById('done-manage-sources-btn'),
      manageSourcesTableBody: document.getElementById('manage-sources-table-body'),
      sourceSearchInput: document.getElementById('source-search-input'),
      unhideAllBtn: document.getElementById('unhide-all-btn'),

      settingsBtn: document.getElementById('settings-btn'),
      settingsModal: document.getElementById('settings-modal'),
      closeSettingsBtn: document.getElementById('close-settings-btn'),
      cancelSettingsBtn: document.getElementById('cancel-settings-btn'),
      settingsForm: document.getElementById('settings-form'),
      settingSwitcherMode: document.getElementById('setting-switcher-mode'),
      settingDefaultTrans: document.getElementById('setting-default-trans'),
      settingTransDuration: document.getElementById('setting-trans-duration'),
      settingVmixHost: document.getElementById('setting-vmix-host'),
      settingVmixPort: document.getElementById('setting-vmix-port'),
      settingMockMode: document.getElementById('setting-mock-mode'),
      settingShowThumbnails: document.getElementById('setting-show-thumbnails'),
      settingNewPassword: document.getElementById('setting-new-password'),
      networkIpsList: document.getElementById('network-ips-list'),
      settingsSaveStatus: document.getElementById('settings-save-status'),

      logoutBtn: document.getElementById('logout-btn'),
      vmixVersionLabel: document.getElementById('vmix-version-label'),
      vmixPresetLabel: document.getElementById('vmix-preset-label')
    };

    this.init();
  }

  async init() {
    this.bindEvents();

    // Check if we are already logged in
    const isAuthed = await API.checkAuth();
    if (isAuthed) {
      this.showApp();
      this.start();
    } else {
      this.showLogin();
    }
  }

  bindEvents() {
    // Thumbnail toggle button
    if (this.dom.thumbToggleBtn) {
      this.dom.thumbToggleBtn.classList.toggle('active', this.showThumbnails);
      this.dom.thumbToggleBtn.addEventListener('click', () => {
        this.showThumbnails = !this.showThumbnails;
        localStorage.setItem('vmix_show_thumbnails', this.showThumbnails);
        this.dom.thumbToggleBtn.classList.toggle('active', this.showThumbnails);
        if (this.dom.settingShowThumbnails) {
          this.dom.settingShowThumbnails.checked = this.showThumbnails;
        }
        if (this.currentState) {
          this.renderSourcesGrid(this.currentState.visibleInputs || []);
        }
      });
    }
    // Login form submission
    this.dom.loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const pwd = this.dom.loginPassword.value;
      this.dom.loginError.classList.add('hidden');
      this.dom.loginBtn.disabled = true;

      try {
        await API.login(pwd);
        this.dom.loginPassword.value = '';
        this.showApp();
        this.start();
      } catch (err) {
        this.dom.loginError.textContent = err.message || 'Incorrect password';
        this.dom.loginError.classList.remove('hidden');
      } finally {
        this.dom.loginBtn.disabled = false;
      }
    });

    // Auth required listener
    window.addEventListener('auth:required', () => {
      this.showLogin();
      this.stopWebSocket();
    });

    // Logout
    this.dom.logoutBtn.addEventListener('click', () => {
      if (confirm('Are you sure you want to log out?')) {
        API.logout();
      }
    });

    // Sound toggle
    if (this.dom.soundToggleBtn) {
      this.dom.soundToggleBtn.addEventListener('click', () => {
        this.soundEnabled = !this.soundEnabled;
        this.dom.soundIconOn.classList.toggle('hidden', !this.soundEnabled);
        this.dom.soundIconOff.classList.toggle('hidden', this.soundEnabled);
        if (this.soundEnabled) this.playTone(800, 0.05);
      });
    }

    // Keyboard Shortcuts (1-9 for inputs, Space for Auto, Enter for Cut)
    window.addEventListener('keydown', (e) => {
      // Ignore if typing in an input field
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
      if (this.dom.appContainer.classList.contains('hidden')) return;

      const key = e.key;
      if (key >= '1' && key <= '9') {
        const inputNum = parseInt(key, 10);
        const target = (this.currentState?.visibleInputs || []).find(i => i.number === inputNum);
        if (target) {
          e.preventDefault();
          this.handleSourceClick(target);
        }
      } else if (e.code === 'Space') {
        e.preventDefault();
        this.vibrate();
        this.playTone(600, 0.06);
        const trans = this.dom.quickTransitionSelect.value;
        const duration = this.currentConfig?.transitionDuration || 500;
        API.executeFunction(trans, { Duration: duration });
      } else if (e.key === 'Enter') {
        e.preventDefault();
        this.vibrate();
        this.playTone(900, 0.04);
        API.executeFunction('Cut');
      }
    });

    // Transition center buttons
    this.dom.btnCut.addEventListener('click', () => {
      this.vibrate();
      this.playTone(900, 0.04);
      API.executeFunction('Cut');
    });

    this.dom.btnAuto.addEventListener('click', () => {
      this.vibrate();
      this.playTone(600, 0.06);
      const trans = this.dom.quickTransitionSelect.value;
      const duration = this.currentConfig?.transitionDuration || 500;
      API.executeFunction(trans, { Duration: duration });
    });

    this.dom.btnFtb.addEventListener('click', () => {
      this.vibrate();
      this.playTone(400, 0.08);
      API.executeFunction('FadeToBlack');
    });

    this.dom.btnQuickplay.addEventListener('click', () => {
      this.vibrate();
      this.playTone(700, 0.05);
      API.executeFunction('QuickPlay');
    });

    this.dom.quickTransitionSelect.addEventListener('change', async (e) => {
      const trans = e.target.value;
      this.updateAutoButtonLabel(trans);
      try {
        await API.saveConfig({ defaultTransition: trans });
        if (this.currentConfig) this.currentConfig.defaultTransition = trans;
      } catch (err) {
        console.error('Failed to save default transition', err);
      }
    });

    // Manage Sources Modal
    this.dom.manageSourcesBtn.addEventListener('click', () => this.openManageSourcesModal());
    this.dom.closeManageSourcesBtn.addEventListener('click', () => this.closeManageSourcesModal());
    this.dom.doneManageSourcesBtn.addEventListener('click', () => this.closeManageSourcesModal());

    this.dom.sourceSearchInput.addEventListener('input', (e) => {
      this.sourceSearchFilter = e.target.value.toLowerCase().trim();
      this.renderManageSourcesTable();
    });

    this.dom.unhideAllBtn.addEventListener('click', async () => {
      if (confirm('Unhide all sources on the switcher?')) {
        await API.unignoreAllSources();
        this.renderManageSourcesTable();
      }
    });

    // Settings Modal
    this.dom.settingsBtn.addEventListener('click', () => this.openSettingsModal());
    this.dom.closeSettingsBtn.addEventListener('click', () => this.closeSettingsModal());
    this.dom.cancelSettingsBtn.addEventListener('click', () => this.closeSettingsModal());

    this.dom.settingsForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      await this.saveSettings();
    });

    // Close modals on overlay click
    [this.dom.manageSourcesModal, this.dom.settingsModal].forEach(modal => {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          modal.classList.add('hidden');
        }
      });
    });
  }

  showLogin() {
    this.dom.loginModal.classList.remove('hidden');
    this.dom.loginModal.classList.add('active');
    this.dom.appContainer.classList.add('hidden');
    this.dom.loginPassword.focus();
  }

  showApp() {
    this.dom.loginModal.classList.add('hidden');
    this.dom.loginModal.classList.remove('active');
    this.dom.appContainer.classList.remove('hidden');
  }

  async start() {
    await this.loadConfig();
    this.connectWebSocket();
  }

  async loadConfig() {
    try {
      this.currentConfig = await API.getConfig();
      if (this.currentConfig.defaultTransition) {
        this.dom.quickTransitionSelect.value = this.currentConfig.defaultTransition;
        this.updateAutoButtonLabel(this.currentConfig.defaultTransition);
      }
      this.updateModeUI(this.currentConfig.switcherMode);
    } catch (err) {
      console.error('Failed to load config', err);
    }
  }

  updateAutoButtonLabel(transName) {
    this.dom.btnAutoLabel.textContent = (transName || 'AUTO').toUpperCase();
  }

  updateModeUI(mode) {
    if (mode === 'preview_take') {
      this.dom.currentModeBadge.textContent = 'Preview + Take Mode';
      this.dom.currentModeBadge.style.backgroundColor = 'rgba(16, 185, 129, 0.2)';
      this.dom.currentModeBadge.style.color = '#6ee7b7';
      this.dom.currentModeDesc.textContent = 'Tapping a source stages it in Preview. Press CUT or AUTO to take.';
    } else {
      this.dom.currentModeBadge.textContent = 'Direct Switch Mode';
      this.dom.currentModeBadge.style.backgroundColor = 'rgba(59, 130, 246, 0.2)';
      this.dom.currentModeBadge.style.color = '#93c5fd';
      this.dom.currentModeDesc.textContent = 'Tapping a source transitions it directly to the Main Output.';
    }
  }

  // Real-time WebSocket connection
  connectWebSocket() {
    if (this.ws) {
      this.ws.close();
    }

    const token = API.getToken();
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws?token=${encodeURIComponent(token)}`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      this.setConnectionStatus('connecting', 'Connecting to vMix...');
      clearInterval(this.pingTimer);
      this.pingTimer = setInterval(() => {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          try { this.ws.send(JSON.stringify({ action: 'ping' })); } catch {}
        }
      }, 15000);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'state') {
          this.handleStateUpdate(msg.data);
        } else if (msg.type === 'connection') {
          if (!msg.data.connected) {
            this.setConnectionStatus('offline', 'vMix Offline (' + (msg.data.error || 'Disconnected') + ')');
          }
        } else if (msg.type === 'auth_error') {
          API.clearToken();
          this.showLogin();
        }
      } catch (err) {
        console.error('Error handling WebSocket message', err);
      }
    };

    this.ws.onclose = () => {
      clearInterval(this.pingTimer);
      this.setConnectionStatus('offline', 'Switcher Disconnected');
      // Auto-reconnect
      clearTimeout(this.wsReconnectTimer);
      this.wsReconnectTimer = setTimeout(() => this.connectWebSocket(), 2000);
    };

    this.ws.onerror = (err) => {
      console.error('WebSocket error', err);
    };
  }

  stopWebSocket() {
    clearInterval(this.pingTimer);
    if (this.wsReconnectTimer) clearTimeout(this.wsReconnectTimer);
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  setConnectionStatus(status, text) {
    this.dom.vmixStatusBadge.className = `status-pill ${status}`;
    this.dom.vmixStatusText.textContent = text;
  }

  // State Updates & Rendering
  handleStateUpdate(state) {
    this.currentState = state;

    // Connection badge
    if (state.isMock) {
      this.setConnectionStatus('mock', 'Simulator Mode (Demo)');
    } else if (state.connected) {
      this.setConnectionStatus('online', 'vMix Online');
    } else {
      this.setConnectionStatus('offline', 'vMix Offline');
    }

    // Version / Preset info
    this.dom.vmixVersionLabel.textContent = `vMix: ${state.version || 'Connected'}`;
    const presetName = state.preset ? state.preset.split(/[\\/]/).pop() : 'None';
    this.dom.vmixPresetLabel.textContent = `Preset: ${presetName}`;

    // Broadcast Badges
    this.dom.recBadge.className = `badge-indicator ${state.recording ? 'active rec' : 'inactive'}`;
    this.dom.streamBadge.className = `badge-indicator ${state.streaming ? 'active stream' : 'inactive'}`;
    this.dom.fullscreenBadge.className = `badge-indicator ${state.fullscreen ? 'active fullscreen' : 'inactive'}`;

    // Active (Program) & Preview monitors
    const activeInput = state.allInputs?.find(i => i.isActive);
    const previewInput = state.allInputs?.find(i => i.isPreview);

    if (activeInput) {
      this.dom.pgmNumber.textContent = activeInput.number;
      this.dom.pgmName.textContent = activeInput.customTitle || activeInput.shortTitle || activeInput.title;
    } else {
      this.dom.pgmNumber.textContent = state.active || '--';
      this.dom.pgmName.textContent = 'None';
    }

    if (previewInput) {
      this.dom.prvNumber.textContent = previewInput.number;
      this.dom.prvName.textContent = previewInput.customTitle || previewInput.shortTitle || previewInput.title;
    } else {
      this.dom.prvNumber.textContent = state.preview || '--';
      this.dom.prvName.textContent = 'None';
    }

    // Ignored Badge
    const ignoredCount = state.ignoredCount || 0;
    if (ignoredCount > 0) {
      this.dom.ignoredCountBadge.textContent = `${ignoredCount} hidden`;
      this.dom.ignoredCountBadge.classList.remove('hidden');
      this.dom.sourceFilterStatus.textContent = `Showing ${state.visibleInputs?.length || 0} of ${state.allInputs?.length || 0} sources (${ignoredCount} hidden)`;
    } else {
      this.dom.ignoredCountBadge.classList.add('hidden');
      this.dom.sourceFilterStatus.textContent = `Showing all ${state.allInputs?.length || 0} sources`;
    }

    // Render Switcher Grid
    this.renderSourcesGrid(state.visibleInputs || []);

    // If Manage Sources modal is open, refresh it as well
    if (!this.dom.manageSourcesModal.classList.contains('hidden')) {
      this.renderManageSourcesTable();
    }
  }

  // Main Switcher Grid Render
  renderSourcesGrid(inputs) {
    if (!inputs || inputs.length === 0) {
      const isOffline = this.currentState && !this.currentState.connected && !this.currentState.isMock;
      if (isOffline) {
        this.dom.sourcesGrid.innerHTML = `
          <div class="loading-placeholder">
            <div style="font-size: 2.2rem;">📡</div>
            <h3 style="color: #f87171;">vMix Not Detected at ${this.escapeHtml(this.currentConfig?.vmixHost || '127.0.0.1')}:${this.currentConfig?.vmixPort || 8088}</h3>
            <p style="max-width: 480px; text-align: center; font-size: 0.9rem; color: var(--text-muted);">
              Make sure vMix is running and the Web Controller is active in <strong>Settings &gt; Web Controller</strong> in vMix.
            </p>
            <div style="display: flex; gap: 10px; margin-top: 10px; flex-wrap: wrap; justify-content: center;">
              <button class="btn btn-primary" id="btn-enable-demo">Enable Demo / Simulator Mode</button>
              <button class="btn btn-secondary" id="btn-open-settings-conn">Connection Settings</button>
            </div>
          </div>
        `;
        const demoBtn = document.getElementById('btn-enable-demo');
        if (demoBtn) demoBtn.addEventListener('click', async () => {
          await API.saveConfig({ mockMode: true });
        });
        const connBtn = document.getElementById('btn-open-settings-conn');
        if (connBtn) connBtn.addEventListener('click', () => this.openSettingsModal());
        return;
      }

      this.dom.sourcesGrid.innerHTML = `
        <div class="loading-placeholder">
          <p>No visible sources found.</p>
          <button class="btn btn-secondary btn-sm" id="empty-manage-btn">Manage Sources (Check hidden)</button>
        </div>
      `;
      const btn = document.getElementById('empty-manage-btn');
      if (btn) btn.addEventListener('click', () => this.openManageSourcesModal());
      return;
    }

    // Render cards efficiently
    const fragment = document.createDocumentFragment();

    inputs.forEach(inp => {
      const card = document.createElement('div');
      card.className = `source-card ${inp.isActive ? 'is-program' : ''} ${inp.isPreview ? 'is-preview' : ''}`;
      card.setAttribute('data-input', inp.number);

      const title = inp.customTitle || inp.shortTitle || inp.title;
      let tallyText = 'STANDBY';
      if (inp.isActive) tallyText = 'PROGRAM / LIVE';
      else if (inp.isPreview) tallyText = 'PREVIEW';

      const overlayHtml = (inp.activeOverlays || []).map(ov => `<span class="overlay-mini-badge">OV${ov}</span>`).join('');
      const audioMuteHtml = inp.muted ? `<span class="audio-mute-badge" title="Muted"><svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/></svg></span>` : '';

      const thumbHtml = this.showThumbnails ? `
        <div class="source-thumb-container">
          <img class="source-thumb-img" src="${API.getThumbnailUrl(inp.number)}" alt="" loading="lazy">
        </div>
      ` : '';

      card.innerHTML = `
        <div class="source-card-header">
          <span class="source-number-badge">${inp.number}</span>
          <div class="source-badges-right">
            ${overlayHtml}
            ${audioMuteHtml}
            <span class="source-type-pill">${inp.type || 'Input'}</span>
          </div>
        </div>
        ${thumbHtml}
        <div class="source-title-main">${this.escapeHtml(title)}</div>
        <div class="source-status-bar">
          <span class="tally-status-text">${tallyText}</span>
        </div>
      `;

      card.addEventListener('click', () => this.handleSourceClick(inp));

      fragment.appendChild(card);
    });

    this.dom.sourcesGrid.innerHTML = '';
    this.dom.sourcesGrid.appendChild(fragment);
  }

  // Handle clicking a source button
  async handleSourceClick(input) {
    this.vibrate();
    this.playTone(850, 0.04);

    const mode = this.currentConfig?.switcherMode || 'direct';
    const defaultTrans = this.dom.quickTransitionSelect.value || this.currentConfig?.defaultTransition || 'Fade';
    const duration = this.currentConfig?.transitionDuration || 500;

    try {
      if (mode === 'direct') {
        // Direct to Program Output with default transition
        await API.switchInput(input.number, defaultTrans, duration);
      } else {
        // Preview + Take mode
        await API.executeFunction('PreviewInput', { Input: input.number });
      }
    } catch (err) {
      console.error('Failed to switch input', err);
    }
  }

  // Manage Sources Modal (Ignore/Hide inputs on app side)
  openManageSourcesModal() {
    this.dom.manageSourcesModal.classList.remove('hidden');
    this.renderManageSourcesTable();
  }

  closeManageSourcesModal() {
    this.dom.manageSourcesModal.classList.add('hidden');
  }

  renderManageSourcesTable() {
    const allInputs = this.currentState?.allInputs || [];
    const filter = this.sourceSearchFilter;

    const filtered = allInputs.filter(inp => {
      if (!filter) return true;
      const numStr = String(inp.number);
      const title = (inp.title || '').toLowerCase();
      const custom = (inp.customTitle || '').toLowerCase();
      return numStr.includes(filter) || title.includes(filter) || custom.includes(filter);
    });

    if (filtered.length === 0) {
      this.dom.manageSourcesTableBody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align: center; color: var(--text-dim); padding: 30px;">
            ${allInputs.length === 0 ? 'No inputs loaded from vMix.' : 'No sources matching search.'}
          </td>
        </tr>
      `;
      return;
    }

    this.dom.manageSourcesTableBody.innerHTML = filtered.map(inp => {
      const isIgnored = Boolean(inp.isIgnored);
      const customName = inp.customTitle || '';

      return `
        <tr class="${isIgnored ? 'row-ignored' : ''}" data-input-row="${inp.number}">
          <td><strong>${inp.number}</strong></td>
          <td>
            <div style="font-weight: 600;">${this.escapeHtml(inp.title)}</div>
            <div style="font-size: 0.75rem; color: var(--text-dim);">${this.escapeHtml(inp.shortTitle || '')}</div>
          </td>
          <td>
            <input type="text"
              class="alias-edit-input"
              data-input="${inp.number}"
              placeholder="Display nickname..."
              value="${this.escapeHtml(customName)}"
            >
          </td>
          <td><span class="source-type-pill">${inp.type || 'Generic'}</span></td>
          <td style="text-align: center;">
            <label class="toggle-switch">
              <input type="checkbox"
                class="source-ignore-toggle"
                data-input="${inp.number}"
                ${!isIgnored ? 'checked' : ''}
              >
              <span class="slider"></span>
            </label>
          </td>
        </tr>
      `;
    }).join('');

    // Attach listeners
    this.dom.manageSourcesTableBody.querySelectorAll('.source-ignore-toggle').forEach(toggle => {
      toggle.addEventListener('change', async (e) => {
        const inputNum = e.target.dataset.input;
        const isVisible = e.target.checked;
        const shouldIgnore = !isVisible;
        this.vibrate();

        try {
          await API.setSourceIgnored(inputNum, shouldIgnore);
        } catch (err) {
          console.error('Failed to update ignore status', err);
          e.target.checked = !isVisible; // revert
        }
      });
    });

    this.dom.manageSourcesTableBody.querySelectorAll('.alias-edit-input').forEach(inputField => {
      inputField.addEventListener('blur', async (e) => {
        const inputNum = e.target.dataset.input;
        const newAlias = e.target.value.trim();
        try {
          await API.setSourceAlias(inputNum, newAlias);
        } catch (err) {
          console.error('Failed to set alias', err);
        }
      });
    });
  }

  // Settings Modal
  async openSettingsModal() {
    this.dom.settingsModal.classList.remove('hidden');
    this.dom.settingsSaveStatus.classList.add('hidden');

    try {
      const cfg = await API.getConfig();
      this.currentConfig = cfg;

      this.dom.settingSwitcherMode.value = cfg.switcherMode || 'direct';
      this.dom.settingDefaultTrans.value = cfg.defaultTransition || 'Fade';
      this.dom.settingTransDuration.value = cfg.transitionDuration || 500;
      this.dom.settingVmixHost.value = cfg.vmixHost || '127.0.0.1';
      this.dom.settingVmixPort.value = cfg.vmixPort || 8088;
      this.dom.settingMockMode.checked = Boolean(cfg.mockMode);
      if (this.dom.settingShowThumbnails) {
        this.dom.settingShowThumbnails.checked = this.showThumbnails;
      }
      this.dom.settingNewPassword.value = '';

      // Load network IPs
      this.loadNetworkIps();
    } catch (err) {
      console.error('Failed to open settings', err);
    }
  }

  closeSettingsModal() {
    this.dom.settingsModal.classList.add('hidden');
  }

  async loadNetworkIps() {
    try {
      const netInfo = await API.getNetworkIps();
      if (!netInfo.ips || netInfo.ips.length === 0) {
        this.dom.networkIpsList.innerHTML = `<p style="color: var(--text-dim);">No external network interface detected.</p>`;
        return;
      }

      this.dom.networkIpsList.innerHTML = netInfo.ips.map(ip => `
        <div class="network-ip-item">
          <span class="network-ip-url">${ip}</span>
          <button type="button" class="copy-btn" data-url="${ip}">Copy</button>
        </div>
      `).join('');

      this.dom.networkIpsList.querySelectorAll('.copy-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          navigator.clipboard.writeText(btn.dataset.url);
          btn.textContent = 'Copied!';
          setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
        });
      });
    } catch (err) {
      this.dom.networkIpsList.innerHTML = `<p style="color: #ef4444;">Failed to load network addresses</p>`;
    }
  }

  async saveSettings() {
    const updates = {
      switcherMode: this.dom.settingSwitcherMode.value,
      defaultTransition: this.dom.settingDefaultTrans.value,
      transitionDuration: parseInt(this.dom.settingTransDuration.value, 10),
      vmixHost: this.dom.settingVmixHost.value.trim(),
      vmixPort: parseInt(this.dom.settingVmixPort.value, 10),
      mockMode: this.dom.settingMockMode.checked
    };

    if (this.dom.settingShowThumbnails) {
      this.showThumbnails = this.dom.settingShowThumbnails.checked;
      localStorage.setItem('vmix_show_thumbnails', this.showThumbnails);
      if (this.dom.thumbToggleBtn) {
        this.dom.thumbToggleBtn.classList.toggle('active', this.showThumbnails);
      }
      if (this.currentState) {
        this.renderSourcesGrid(this.currentState.visibleInputs || []);
      }
    }

    const newPwd = this.dom.settingNewPassword.value.trim();
    if (newPwd) {
      if (newPwd.length < 3) {
        this.showSettingsStatus('Password must be at least 3 characters', false);
        return;
      }
      updates.newPassword = newPwd;
    }

    try {
      const res = await API.saveConfig(updates);
      this.currentConfig = res.config;
      this.dom.quickTransitionSelect.value = res.config.defaultTransition;
      this.updateAutoButtonLabel(res.config.defaultTransition);
      this.updateModeUI(res.config.switcherMode);

      this.showSettingsStatus('Settings saved successfully!', true);

      setTimeout(() => {
        this.closeSettingsModal();
      }, 800);
    } catch (err) {
      this.showSettingsStatus(err.message || 'Failed to save settings', false);
    }
  }

  showSettingsStatus(text, isSuccess) {
    const el = this.dom.settingsSaveStatus;
    el.textContent = text;
    el.className = `status-msg ${isSuccess ? 'success' : 'error'}`;
    el.classList.remove('hidden');
  }

  // Utilities
  vibrate() {
    if ('vibrate' in navigator) {
      try { navigator.vibrate(25); } catch {}
    }
  }

  playTone(freq = 800, duration = 0.05) {
    if (!this.soundEnabled) return;
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!this.audioCtx && AudioContext) {
        this.audioCtx = new AudioContext();
      }
      if (this.audioCtx) {
        if (this.audioCtx.state === 'suspended') {
          this.audioCtx.resume();
        }
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, this.audioCtx.currentTime);
        gain.gain.setValueAtTime(0.06, this.audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.0001, this.audioCtx.currentTime + duration);
        osc.connect(gain);
        gain.connect(this.audioCtx.destination);
        osc.start();
        osc.stop(this.audioCtx.currentTime + duration);
      }
    } catch {}
  }

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  window.app = new SwitcherApp();
});
