// Main Switcher Application Controller

class SwitcherApp {
  constructor() {
    this.ws = null;
    this.wsReconnectTimer = null;
    this.currentState = null;
    this.currentConfig = null;
    this.sourceSearchFilter = '';
    this.soundEnabled = true;
    this.showThumbnails = localStorage.getItem('vmix_show_thumbnails') !== 'false';
    this.previewFps = parseFloat(localStorage.getItem('vmix_preview_fps')) || 4;
    this.visibleThumbs = new WeakSet();
    this.thumbObserver = null;
    this.audioCtx = null;
    this.pingTimer = null;
    this.currentView = 'switcher';
    this.clockTimer = null;
    this.recordingStartTime = null;

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
      recTimer: document.getElementById('rec-timer'),
      streamBadge: document.getElementById('stream-badge'),
      externalBadge: document.getElementById('external-badge'),
      fullscreenBadge: document.getElementById('fullscreen-badge'),

      // App Mode Tabs & View Panels
      tabSwitcher: document.getElementById('tab-switcher'),
      tabAudio: document.getElementById('tab-audio'),
      tabMultiview: document.getElementById('tab-multiview'),
      viewSwitcher: document.getElementById('view-switcher'),
      viewAudio: document.getElementById('view-audio'),
      viewMultiview: document.getElementById('view-multiview'),

      // Live Video Monitors & Method Switcher
      pgmMonitorImg: document.getElementById('pgm-monitor-img'),
      prvMonitorImg: document.getElementById('prv-monitor-img'),
      methodDirectBtn: document.getElementById('method-direct-btn'),
      methodPreviewBtn: document.getElementById('method-preview-btn'),

      soundToggleBtn: document.getElementById('sound-toggle-btn'),
      soundIconOn: document.getElementById('sound-icon-on'),
      soundIconOff: document.getElementById('sound-icon-off'),
      thumbToggleBtn: document.getElementById('thumb-toggle-btn'),

      pgmNumber: document.getElementById('pgm-number'),
      pgmName: document.getElementById('pgm-name'),
      prvNumber: document.getElementById('prv-number'),
      prvName: document.getElementById('prv-name'),
      pgmThumbMode: document.getElementById('pgm-thumb-mode'),
      prvThumbMode: document.getElementById('prv-thumb-mode'),
      mvThumbMode: document.getElementById('mv-thumb-mode'),

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

      // Audio Console
      audioChannelsGrid: document.getElementById('audio-channels-grid'),
      audioLiveCount: document.getElementById('audio-live-count'),
      audioMuteAllBtn: document.getElementById('audio-mute-all-btn'),
      audioLiveAllBtn: document.getElementById('audio-live-all-btn'),

      // Big Screen Multiviewer / Preview Mode
      multiviewClock: document.getElementById('multiview-clock'),
      multiviewWallGrid: document.getElementById('multiview-wall-grid'),
      cornerPosLeftBtn: document.getElementById('corner-pos-left-btn'),
      cornerPosRightBtn: document.getElementById('corner-pos-right-btn'),
      mvPgmTitle: document.getElementById('mv-pgm-title'),
      mvPrvTitle: document.getElementById('mv-prv-title'),
      mvPgmImg: document.getElementById('mv-pgm-img'),
      mvPrvImg: document.getElementById('mv-prv-img'),
      mvPgmNum: document.getElementById('mv-pgm-num'),
      mvPgmName: document.getElementById('mv-pgm-name'),
      mvPrvNum: document.getElementById('mv-prv-num'),
      mvPrvName: document.getElementById('mv-prv-name'),
      multiviewCamsGrid: document.getElementById('multiview-cams-grid'),
      mvFullscreenToggleBtn: document.getElementById('mv-fullscreen-toggle-btn'),

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
      settingPreviewFps: document.getElementById('setting-preview-fps'),
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
    this.startClock();

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
    // App Mode Navigation Tabs
    if (this.dom.tabSwitcher) {
      this.dom.tabSwitcher.addEventListener('click', () => this.switchView('switcher'));
    }
    if (this.dom.tabAudio) {
      this.dom.tabAudio.addEventListener('click', () => this.switchView('audio'));
    }
    if (this.dom.tabMultiview) {
      this.dom.tabMultiview.addEventListener('click', () => this.switchView('multiview'));
    }

    // Direct vs Preview + Take Switching Method Pills
    if (this.dom.methodDirectBtn) {
      this.dom.methodDirectBtn.addEventListener('click', () => this.setSwitcherMode('direct'));
    }
    if (this.dom.methodPreviewBtn) {
      this.dom.methodPreviewBtn.addEventListener('click', () => this.setSwitcherMode('preview_take'));
    }

    // Interactive Broadcast Controls (REC, STREAM, EXTERNAL, FULLSCREEN)
    if (this.dom.recBadge) {
      this.dom.recBadge.addEventListener('click', async () => {
        this.vibrate();
        this.playTone(500, 0.05);
        try {
          await API.toggleRecording();
        } catch (err) {
          console.error('Failed to toggle recording', err);
        }
      });
    }

    if (this.dom.streamBadge) {
      this.dom.streamBadge.addEventListener('click', async () => {
        this.vibrate();
        this.playTone(600, 0.05);
        try {
          await API.toggleStreaming();
        } catch (err) {
          console.error('Failed to toggle streaming', err);
        }
      });
    }

    if (this.dom.externalBadge) {
      this.dom.externalBadge.addEventListener('click', async () => {
        this.vibrate();
        this.playTone(700, 0.05);
        try {
          await API.toggleExternal();
        } catch (err) {
          console.error('Failed to toggle external output', err);
        }
      });
    }

    if (this.dom.fullscreenBadge) {
      this.dom.fullscreenBadge.addEventListener('click', () => this.toggleFullscreen());
    }
    if (this.dom.mvFullscreenToggleBtn) {
      this.dom.mvFullscreenToggleBtn.addEventListener('click', () => this.toggleFullscreen());
    }

    // Preview Mode Corner Position Controls
    const savedCorner = localStorage.getItem('vmix_preview_corner') || 'left';
    this.setCornerPosition(savedCorner);

    if (this.dom.cornerPosLeftBtn) {
      this.dom.cornerPosLeftBtn.addEventListener('click', () => this.setCornerPosition('left'));
    }
    if (this.dom.cornerPosRightBtn) {
      this.dom.cornerPosRightBtn.addEventListener('click', () => this.setCornerPosition('right'));
    }

    // Audio Master Actions
    if (this.dom.audioMuteAllBtn) {
      this.dom.audioMuteAllBtn.addEventListener('click', () => this.muteAllAudio());
    }
    if (this.dom.audioLiveAllBtn) {
      this.dom.audioLiveAllBtn.addEventListener('click', () => this.unmuteAllAudio());
    }

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
        if (this.showThumbnails) {
          this.startThumbnailRefresh();
        } else {
          this.stopThumbnailRefresh();
        }
        if (this.currentState) {
          this.renderSourcesGrid(this.currentState.visibleInputs || [], true);
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
    this.startThumbnailRefresh();
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
    const isPreviewTake = mode === 'preview_take';
    if (this.dom.methodDirectBtn) {
      this.dom.methodDirectBtn.classList.toggle('active', !isPreviewTake);
    }
    if (this.dom.methodPreviewBtn) {
      this.dom.methodPreviewBtn.classList.toggle('active', isPreviewTake);
    }

    if (this.dom.currentModeBadge) {
      this.dom.currentModeBadge.classList.toggle('is-preview-take', isPreviewTake);
      this.dom.currentModeBadge.classList.toggle('is-direct', !isPreviewTake);
    }

    if (isPreviewTake) {
      this.dom.currentModeBadge.textContent = 'Preview + Take Mode';
      this.dom.currentModeDesc.textContent = 'Tapping a source stages it in Preview. Press CUT or AUTO to take.';
    } else {
      this.dom.currentModeBadge.textContent = 'Direct Switch Mode';
      this.dom.currentModeDesc.textContent = 'Tapping a source transitions it directly to the Main Output.';
    }
  }

  async setSwitcherMode(mode) {
    if (this.currentConfig) {
      this.currentConfig.switcherMode = mode;
    }
    this.updateModeUI(mode);
    if (this.dom.settingSwitcherMode) {
      this.dom.settingSwitcherMode.value = mode;
    }
    try {
      await API.saveConfig({ switcherMode: mode });
    } catch (err) {
      console.error('Failed to update switcher mode', err);
    }
  }

  switchView(view) {
    this.currentView = view;
    if (this.dom.tabSwitcher) this.dom.tabSwitcher.classList.toggle('active', view === 'switcher');
    if (this.dom.tabAudio) this.dom.tabAudio.classList.toggle('active', view === 'audio');
    if (this.dom.tabMultiview) this.dom.tabMultiview.classList.toggle('active', view === 'multiview');

    if (this.dom.viewSwitcher) this.dom.viewSwitcher.classList.toggle('hidden', view !== 'switcher');
    if (this.dom.viewAudio) this.dom.viewAudio.classList.toggle('hidden', view !== 'audio');
    if (this.dom.viewMultiview) this.dom.viewMultiview.classList.toggle('hidden', view !== 'multiview');

    if (this.currentState) {
      if (view === 'audio') {
        this.renderAudioMixer(this.currentState.allInputs || []);
      } else if (view === 'multiview') {
        this.renderMultiviewGrid(this.currentState.visibleInputs || []);
      } else {
        this.renderSourcesGrid(this.currentState.visibleInputs || []);
      }
    }
  }

  toggleFullscreen() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      }
    }
  }

  setCornerPosition(pos) {
    const isRight = pos === 'right';
    if (this.dom.multiviewWallGrid) {
      this.dom.multiviewWallGrid.classList.toggle('corner-right', isRight);
      this.dom.multiviewWallGrid.classList.toggle('corner-left', !isRight);
    }
    if (this.dom.cornerPosLeftBtn) this.dom.cornerPosLeftBtn.classList.toggle('active', !isRight);
    if (this.dom.cornerPosRightBtn) this.dom.cornerPosRightBtn.classList.toggle('active', isRight);
    localStorage.setItem('vmix_preview_corner', isRight ? 'right' : 'left');
  }

  startClock() {
    if (this.clockTimer) clearInterval(this.clockTimer);
    this.clockTimer = setInterval(() => {
      // Production clock
      const now = new Date();
      const timeStr = now.toTimeString().split(' ')[0];
      if (this.dom.multiviewClock) {
        this.dom.multiviewClock.textContent = timeStr;
      }

      // Recording elapsed timer
      if (this.recordingStartTime && this.dom.recTimer) {
        const elapsedSec = Math.floor((Date.now() - this.recordingStartTime) / 1000);
        const hrs = Math.floor(elapsedSec / 3600);
        const mins = Math.floor((elapsedSec % 3600) / 60);
        const secs = elapsedSec % 60;
        const pad = (n) => String(n).padStart(2, '0');
        this.dom.recTimer.textContent = hrs > 0 ? `${hrs}:${pad(mins)}:${pad(secs)}` : `${pad(mins)}:${pad(secs)}`;
      }
    }, 500);
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
    this.stopThumbnailRefresh();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  setPreviewFps(fps) {
    const next = Math.min(10, Math.max(0.5, parseFloat(fps) || 4));
    if (next === this.previewFps) return;
    this.previewFps = next;
    localStorage.setItem('vmix_preview_fps', String(next));
    this.startThumbnailRefresh();
  }

  getPreviewIntervalMs() {
    return Math.max(80, Math.round(1000 / this.previewFps));
  }

  // Only poll images that are on screen, and never stack requests on a slow link
  trackThumbVisibility(img) {
    if (!this.thumbObserver) {
      this.thumbObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            this.visibleThumbs.add(entry.target);
          } else {
            this.visibleThumbs.delete(entry.target);
          }
        });
      }, { rootMargin: '250px' });
    }
    if (!img.dataset.thumbTracked) {
      img.dataset.thumbTracked = '1';
      this.thumbObserver.observe(img);
      this.visibleThumbs.add(img);
    }
  }

  refreshThumb(img) {
    const inputNum = img.getAttribute('data-thumb-input');
    if (!inputNum) return;
    this.trackThumbVisibility(img);
    if (!this.visibleThumbs.has(img)) return;
    if (img.dataset.thumbLoading === '1') return;

    img.dataset.thumbLoading = '1';
    img.onload = img.onerror = () => { img.dataset.thumbLoading = '0'; };
    img.src = `${API.getThumbnailUrl(inputNum)}&_t=${Date.now()}`;
  }

  startThumbnailRefresh() {
    this.stopThumbnailRefresh();
    if (!this.showThumbnails) return;
    this.thumbTimer = setInterval(() => {
      if (!this.showThumbnails || this.dom.appContainer.classList.contains('hidden')) return;
      if (document.hidden) return;

      // Refresh Switcher Grid cards
      const imgs = this.dom.sourcesGrid.querySelectorAll('.source-thumb-img');
      imgs.forEach(img => this.refreshThumb(img));

      // Refresh Live Monitors (Program & Preview)
      if (this.currentState) {
        const activeNum = this.currentState.active || 'active';
        const previewNum = this.currentState.preview || 'preview';
        // Input changed on a monitor: force an immediate re-fetch (bypasses load gating)
        if (activeNum !== this.lastMonitoredActive) {
          this.lastMonitoredActive = activeNum;
          [this.dom.pgmMonitorImg, this.dom.mvPgmImg].forEach(img => {
            if (!img) return;
            img.dataset.thumbLoading = '0';
            img.setAttribute('data-thumb-input', activeNum);
            img.src = `${API.getThumbnailUrl(activeNum)}&_t=${Date.now()}`;
          });
        }
        if (previewNum !== this.lastMonitoredPreview) {
          this.lastMonitoredPreview = previewNum;
          [this.dom.prvMonitorImg, this.dom.mvPrvImg].forEach(img => {
            if (!img) return;
            img.dataset.thumbLoading = '0';
            img.setAttribute('data-thumb-input', previewNum);
            img.src = `${API.getThumbnailUrl(previewNum)}&_t=${Date.now()}`;
          });
        }

        [this.dom.pgmMonitorImg, this.dom.mvPgmImg].forEach(img => {
          if (img) img.setAttribute('data-thumb-input', activeNum);
        });
        [this.dom.prvMonitorImg, this.dom.mvPrvImg].forEach(img => {
          if (img) img.setAttribute('data-thumb-input', previewNum);
        });

        [this.dom.pgmMonitorImg, this.dom.prvMonitorImg, this.dom.mvPgmImg, this.dom.mvPrvImg]
          .forEach(img => { if (img) this.refreshThumb(img); });
      }

      // Refresh Multiviewer Camera grid thumbnails
      if (this.dom.multiviewCamsGrid) {
        const mvImgs = this.dom.multiviewCamsGrid.querySelectorAll('.mv-cam-img');
        mvImgs.forEach(img => this.refreshThumb(img));
      }
    }, this.getPreviewIntervalMs());
  }

  stopThumbnailRefresh() {
    if (this.thumbTimer) {
      clearInterval(this.thumbTimer);
      this.thumbTimer = null;
    }
  }

  setConnectionStatus(status, text) {
    this.dom.vmixStatusBadge.className = `status-pill ${status}`;
    this.dom.vmixStatusText.textContent = text;
  }

  // Snapshot pill: IMG:LIVE = real JPEG from vMix, anything else = graphic
  // placeholder (with the reason in the tooltip).
  updateThumbPill(el, state) {
    if (!el) return;
    const mode = state.thumbnailMode || 'starting';
    const detail = state.thumbnailDetail || '';
    const map = {
      live: ['IMG:LIVE', 'is-live', 'Live snapshot from vMix'],
      starting: ['IMG:LOAD', 'is-waiting', detail || 'Requesting snapshots from vMix…'],
      paused: ['IMG:OFF', 'is-off', detail || 'Snapshots paused — vMix reported save errors'],
      remote: ['IMG:OFF', 'is-off', detail || 'Run the switcher on the vMix PC for live images'],
      offline: ['IMG:OFF', 'is-off', 'vMix offline'],
      mock: ['DEMO', 'is-off', 'Simulator mode — demo graphics'],
    };
    const [text, cls, title] = map[mode] || map.starting;
    if (el.textContent !== text) el.textContent = text;
    const nextCls = `thumb-mode-pill ${cls}`;
    if (el.className !== nextCls) el.className = nextCls;
    if (title && el.title !== title) el.title = title;
  }

  // State Updates & Rendering
  handleStateUpdate(state) {
    this.currentState = state;

    // Live preview refresh rate (server is the source of truth)
    if (state.previewFps && state.previewFps !== this.previewFps) {
      this.setPreviewFps(state.previewFps);
    }

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
    if (state.recording) {
      if (!this.recordingStartTime) {
        this.recordingStartTime = Date.now();
      }
    } else {
      this.recordingStartTime = null;
      if (this.dom.recTimer) this.dom.recTimer.textContent = '';
    }

    this.dom.streamBadge.className = `badge-indicator ${state.streaming ? 'active stream' : 'inactive'}`;
    if (this.dom.externalBadge) {
      this.dom.externalBadge.className = `badge-indicator ${state.external ? 'active external' : 'inactive'}`;
    }
    this.dom.fullscreenBadge.className = `badge-indicator ${state.fullscreen ? 'active fullscreen' : 'inactive'}`;

    // FTB Button active indicator
    if (this.dom.btnFtb) {
      const isFtb = Boolean(state.fadeToBlack);
      this.dom.btnFtb.classList.toggle('active', isFtb);
      this.dom.btnFtb.textContent = isFtb ? 'FTB ON' : 'FTB';
    }

    // Active (Program) & Preview monitors
    const activeInput = state.allInputs?.find(i => i.isActive);
    const previewInput = state.allInputs?.find(i => i.isPreview);
    const activeNum = activeInput ? activeInput.number : (state.active || 'active');
    const previewNum = previewInput ? previewInput.number : (state.preview || 'preview');
    const activeTitle = activeInput ? (activeInput.customTitle || activeInput.shortTitle || activeInput.title) : 'None';
    const previewTitle = previewInput ? (previewInput.customTitle || previewInput.shortTitle || previewInput.title) : 'None';

    this.dom.pgmNumber.textContent = activeNum || '--';
    this.dom.pgmName.textContent = activeTitle;
    this.dom.prvNumber.textContent = previewNum || '--';
    this.dom.prvName.textContent = previewTitle;

    // Snapshot LIVE vs placeholder pills (vMix has no video-feed API)
    this.updateThumbPill(this.dom.pgmThumbMode, state);
    this.updateThumbPill(this.dom.prvThumbMode, state);
    this.updateThumbPill(this.dom.mvThumbMode, state);

    // Update Live Monitor Images — steady-state refresh is owned by the
    // thumbnail interval loop (with visibility + load gating). Here we only
    // touch the <img> when the routed input number actually changed, so a
    // state broadcast every ~300ms doesn't restart every image download and
    // hammer vMix into timeouts (which used to fall back to SVG placeholders).
    const now = Date.now();
    if (activeNum !== this.lastMonitoredActive) {
      this.lastMonitoredActive = activeNum;
      [this.dom.pgmMonitorImg, this.dom.mvPgmImg].forEach(img => {
        if (!img) return;
        img.dataset.thumbLoading = '0';
        img.setAttribute('data-thumb-input', activeNum);
        img.src = `${API.getThumbnailUrl(activeNum)}&_t=${now}`;
      });
    } else {
      [this.dom.pgmMonitorImg, this.dom.mvPgmImg].forEach(img => {
        if (img && !img.getAttribute('data-thumb-input')) img.setAttribute('data-thumb-input', activeNum);
      });
    }
    if (previewNum !== this.lastMonitoredPreview) {
      this.lastMonitoredPreview = previewNum;
      [this.dom.prvMonitorImg, this.dom.mvPrvImg].forEach(img => {
        if (!img) return;
        img.dataset.thumbLoading = '0';
        img.setAttribute('data-thumb-input', previewNum);
        img.src = `${API.getThumbnailUrl(previewNum)}&_t=${now}`;
      });
    } else {
      [this.dom.prvMonitorImg, this.dom.mvPrvImg].forEach(img => {
        if (img && !img.getAttribute('data-thumb-input')) img.setAttribute('data-thumb-input', previewNum);
      });
    }
    if (this.dom.mvPgmTitle) this.dom.mvPgmTitle.textContent = activeTitle;
    if (this.dom.mvPrvTitle) this.dom.mvPrvTitle.textContent = previewTitle;
    if (this.dom.mvPgmNum) this.dom.mvPgmNum.textContent = activeNum || '--';
    if (this.dom.mvPgmName) this.dom.mvPgmName.textContent = activeTitle;
    if (this.dom.mvPrvNum) this.dom.mvPrvNum.textContent = previewNum || '--';
    if (this.dom.mvPrvName) this.dom.mvPrvName.textContent = previewTitle;

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

    // Render current active view
    if (this.currentView === 'audio') {
      this.renderAudioMixer(state.allInputs || []);
    } else if (this.currentView === 'multiview') {
      this.renderMultiviewGrid(state.visibleInputs || []);
    } else {
      this.renderSourcesGrid(state.visibleInputs || []);
    }

    // If Manage Sources modal is open, refresh it as well
    if (!this.dom.manageSourcesModal.classList.contains('hidden')) {
      this.renderManageSourcesTable();
    }
  }

  // Main Switcher Grid Render
  renderSourcesGrid(inputs, forceRebuild = false) {
    if (!inputs || inputs.length === 0) {
      const isOffline = this.currentState && !this.currentState.connected && !this.currentState.isMock;
      if (isOffline) {
        this.dom.sourcesGrid.innerHTML = `
          <div class="empty-state">
            <h3 class="empty-title">vMix Not Detected at ${this.escapeHtml(this.currentConfig?.vmixHost || '127.0.0.1')}:${this.currentConfig?.vmixPort || 8088}</h3>
            <p class="empty-text">
              Make sure vMix is running and the Web Controller is active in <strong>Settings &gt; Web Controller</strong> in vMix.
            </p>
            <div class="empty-actions">
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
        <div class="empty-state">
          <h3 class="empty-title">No visible sources</h3>
          <p class="empty-text">Every vMix input is hidden from the switcher. Show them again in Manage Sources.</p>
          <div class="empty-actions">
            <button class="btn btn-secondary btn-sm" id="empty-manage-btn">Manage Sources</button>
          </div>
        </div>
      `;
      const btn = document.getElementById('empty-manage-btn');
      if (btn) btn.addEventListener('click', () => this.openManageSourcesModal());
      return;
    }

    // Check if we can do an in-place update without wiping the DOM
    const existingCards = this.dom.sourcesGrid.querySelectorAll('.source-card');
    const existingNums = Array.from(existingCards).map(c => c.getAttribute('data-input'));
    const newNums = inputs.map(i => String(i.number));

    const canUpdateInPlace = !forceRebuild &&
      existingNums.length === newNums.length &&
      existingNums.every((val, idx) => val === newNums[idx]);

    if (canUpdateInPlace) {
      existingCards.forEach((card, idx) => {
        const inp = inputs[idx];
        card.classList.toggle('is-program', Boolean(inp.isActive));
        card.classList.toggle('is-preview', Boolean(inp.isPreview));

        let tallyText = 'STANDBY';
        if (inp.isActive) tallyText = 'PROGRAM / LIVE';
        else if (inp.isPreview) tallyText = 'PREVIEW';
        const tallyStatusEl = card.querySelector('.tally-status-text');
        if (tallyStatusEl && tallyStatusEl.textContent !== tallyText) {
          tallyStatusEl.textContent = tallyText;
        }

        const title = inp.customTitle || inp.shortTitle || inp.title;
        const titleEl = card.querySelector('.source-title-main');
        if (titleEl && titleEl.textContent !== title) {
          titleEl.textContent = title;
        }

        const badgesRightEl = card.querySelector('.source-badges-right');
        if (badgesRightEl) {
          const overlayHtml = (inp.activeOverlays || []).map(ov => `<span class="overlay-mini-badge">OV${ov}</span>`).join('');
          const audioMuteHtml = inp.muted ? `<span class="audio-mute-badge" title="Muted"><svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/></svg></span>` : '';
          const typeHtml = `<span class="source-type-pill">${this.escapeHtml(inp.type || 'Input')}</span>`;
          const newBadgesHtml = overlayHtml + audioMuteHtml + typeHtml;
          if (badgesRightEl.innerHTML !== newBadgesHtml) {
            badgesRightEl.innerHTML = newBadgesHtml;
          }
        }
      });
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
          <img class="source-thumb-img" data-thumb-input="${inp.number}" src="${API.getThumbnailUrl(inp.number)}" alt="" loading="lazy">
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

  // ==================== AUDIO / MIC MIXER CONSOLE ====================
  renderAudioMixer(inputs) {
    if (!this.dom.audioChannelsGrid) return;
    if (!inputs || inputs.length === 0) {
      this.dom.audioChannelsGrid.innerHTML = `
        <div class="loading-placeholder">
          <p>No audio channels detected.</p>
        </div>
      `;
      return;
    }

    const liveCount = inputs.filter(i => !i.muted).length;
    if (this.dom.audioLiveCount) {
      this.dom.audioLiveCount.textContent = `${liveCount} Live Audio`;
    }

    // If an input slider is currently being interacted with, avoid destroying the DOM
    const activeEl = document.activeElement;
    const isInteracting = activeEl && this.dom.audioChannelsGrid.contains(activeEl);

    if (isInteracting) {
      inputs.forEach(inp => {
        const card = this.dom.audioChannelsGrid.querySelector(`[data-audio-input="${inp.number}"]`);
        if (!card) return;
        const isLive = !inp.muted;
        card.classList.toggle('is-live', isLive);
        card.classList.toggle('is-muted', !isLive);

        const btn = card.querySelector('.audio-mute-toggle-btn');
        if (btn) {
          btn.className = `audio-mute-toggle-btn ${isLive ? 'live' : 'muted'}`;
          btn.textContent = isLive ? 'LIVE / ON AIR' : 'MUTED';
        }

        const vuFill = card.querySelector('.audio-vu-fill');
        if (vuFill) {
          const vol = inp.volume !== undefined ? inp.volume : 100;
          const pct = isLive ? Math.max(15, Math.min(100, Math.round(vol * 0.9))) : 0;
          vuFill.style.width = `${pct}%`;
        }
      });
      return;
    }

    const fragment = document.createDocumentFragment();

    inputs.forEach(inp => {
      const isLive = !inp.muted;
      const vol = Math.round(inp.volume !== undefined ? inp.volume : 100);
      const title = inp.customTitle || inp.shortTitle || inp.title;

      const card = document.createElement('div');
      card.className = `audio-card ${isLive ? 'is-live' : 'is-muted'}`;
      card.setAttribute('data-audio-input', inp.number);

      card.innerHTML = `
        <div class="audio-card-header">
          <div class="audio-title-group">
            <span class="source-number-badge">${inp.number}</span>
            <div>
              <div class="audio-card-title" title="${this.escapeHtml(title)}">${this.escapeHtml(title)}</div>
              <div class="audio-card-type">${inp.type || 'Audio'}</div>
            </div>
          </div>
          <button type="button" class="audio-mute-toggle-btn ${isLive ? 'live' : 'muted'}" data-input="${inp.number}">
            ${isLive ? 'LIVE / ON AIR' : 'MUTED'}
          </button>
        </div>
        <div class="audio-fader-row">
          <div class="audio-fader-labels">
            <span>Fader Level</span>
            <span class="audio-vol-text">${vol}%</span>
          </div>
          <input type="range" class="audio-fader-slider" min="0" max="100" value="${vol}" data-input="${inp.number}">
          <div class="audio-vu-meter-bar">
            <div class="audio-vu-fill" style="width: ${isLive ? Math.max(15, Math.round(vol * 0.9)) : 0}%;"></div>
          </div>
        </div>
      `;

      // Mute Toggle Button Click
      const muteBtn = card.querySelector('.audio-mute-toggle-btn');
      muteBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        this.vibrate();
        this.playTone(isLive ? 350 : 700, 0.04);
        try {
          await API.toggleAudio(inp.number);
        } catch (err) {
          console.error('Failed to toggle audio', err);
        }
      });

      // Slider Change / Input
      const slider = card.querySelector('.audio-fader-slider');
      const volText = card.querySelector('.audio-vol-text');
      const vuFill = card.querySelector('.audio-vu-fill');

      slider.addEventListener('input', (e) => {
        const val = parseInt(e.target.value, 10);
        volText.textContent = `${val}%`;
        if (isLive) {
          vuFill.style.width = `${Math.max(15, Math.round(val * 0.9))}%`;
        }
      });

      slider.addEventListener('change', async (e) => {
        const val = parseInt(e.target.value, 10);
        try {
          await API.setVolume(inp.number, val);
        } catch (err) {
          console.error('Failed to set volume', err);
        }
      });

      fragment.appendChild(card);
    });

    this.dom.audioChannelsGrid.innerHTML = '';
    this.dom.audioChannelsGrid.appendChild(fragment);
  }

  async muteAllAudio() {
    if (!this.currentState?.allInputs) return;
    this.vibrate();
    this.playTone(300, 0.08);
    for (const inp of this.currentState.allInputs) {
      if (!inp.muted) {
        try {
          await API.executeFunction('AudioOff', { Input: inp.number });
        } catch {}
      }
    }
  }

  async unmuteAllAudio() {
    if (!this.currentState?.allInputs) return;
    this.vibrate();
    this.playTone(700, 0.08);
    for (const inp of this.currentState.allInputs) {
      if (inp.muted) {
        try {
          await API.executeFunction('AudioOn', { Input: inp.number });
        } catch {}
      }
    }
  }

  // ==================== BIG SCREEN MULTIVIEWER / PREVIEW MODE ====================
  renderMultiviewGrid(inputs) {
    if (!this.dom.multiviewCamsGrid) return;
    if (!inputs || inputs.length === 0) {
      this.dom.multiviewCamsGrid.innerHTML = `
        <div class="loading-placeholder">
          <p>No multiview camera inputs detected.</p>
        </div>
      `;
      return;
    }

    const existingTiles = this.dom.multiviewCamsGrid.querySelectorAll('.multiview-cam-tile');
    const existingNums = Array.from(existingTiles).map(t => t.getAttribute('data-mv-input'));
    const newNums = inputs.map(i => String(i.number));

    const canUpdateInPlace = existingNums.length === newNums.length &&
      existingNums.every((val, idx) => val === newNums[idx]);

    if (canUpdateInPlace) {
      existingTiles.forEach((tile, idx) => {
        const inp = inputs[idx];
        tile.classList.toggle('is-program', Boolean(inp.isActive));
        tile.classList.toggle('is-preview', Boolean(inp.isPreview));

        const statusPill = tile.querySelector('.mv-cam-status-pill');
        if (statusPill) {
          statusPill.className = `mv-cam-status-pill ${inp.isActive ? 'live' : (inp.isPreview ? 'prv' : '')}`;
          statusPill.textContent = inp.isActive ? 'ON AIR' : (inp.isPreview ? 'NEXT' : '');
        }

        const titleEl = tile.querySelector('.mv-cam-title');
        const title = inp.customTitle || inp.shortTitle || inp.title;
        if (titleEl && titleEl.textContent !== title) {
          titleEl.textContent = title;
        }
      });
      return;
    }

    const fragment = document.createDocumentFragment();

    inputs.forEach(inp => {
      const title = inp.customTitle || inp.shortTitle || inp.title;
      const tile = document.createElement('div');
      tile.className = `multiview-cam-tile ${inp.isActive ? 'is-program' : (inp.isPreview ? 'is-preview' : '')}`;
      tile.setAttribute('data-mv-input', inp.number);

      tile.innerHTML = `
        <img class="mv-cam-img" data-thumb-input="${inp.number}" src="${API.getThumbnailUrl(inp.number)}" alt="" loading="lazy">
        <span class="mv-cam-badge">CAM ${inp.number}</span>
        <span class="mv-cam-status-pill ${inp.isActive ? 'live' : (inp.isPreview ? 'prv' : '')}">${inp.isActive ? 'ON AIR' : (inp.isPreview ? 'NEXT' : '')}</span>
        <div class="mv-cam-take-action">
          <button type="button" class="mv-take-live-btn" data-input="${inp.number}">Put Live in Corner</button>
        </div>
        <div class="mv-cam-title">${this.escapeHtml(title)}</div>
      `;

      // Click card or "Put Live" button to switch and put into the corner
      tile.addEventListener('click', () => {
        this.vibrate();
        this.playTone(850, 0.04);
        API.switchInput(inp.number);
      });

      const takeBtn = tile.querySelector('.mv-take-live-btn');
      if (takeBtn) {
        takeBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.vibrate();
          this.playTone(850, 0.04);
          API.switchInput(inp.number);
        });
      }

      fragment.appendChild(tile);
    });

    this.dom.multiviewCamsGrid.innerHTML = '';
    this.dom.multiviewCamsGrid.appendChild(fragment);
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
    // Do not overwrite table if user is currently typing in an input inside the table
    if (document.activeElement && this.dom.manageSourcesTableBody && this.dom.manageSourcesTableBody.contains(document.activeElement)) {
      return;
    }

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
          <td colspan="5" class="table-empty">
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
            <div class="table-title">${this.escapeHtml(inp.title)}</div>
            <div class="table-sub">${this.escapeHtml(inp.shortTitle || '')}</div>
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
          <td class="table-center">
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
      inputField.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          inputField.blur();
        }
      });
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
      if (this.dom.settingPreviewFps) {
        this.dom.settingPreviewFps.value = String(cfg.previewFps || this.previewFps);
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
        this.dom.networkIpsList.innerHTML = `<p class="network-ip-empty">No external network interface detected.</p>`;
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
      this.dom.networkIpsList.innerHTML = `<p class="network-ip-error">Failed to load network addresses</p>`;
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

    if (this.dom.settingPreviewFps) {
      this.setPreviewFps(parseFloat(this.dom.settingPreviewFps.value));
      updates.previewFps = this.previewFps;
    }

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
