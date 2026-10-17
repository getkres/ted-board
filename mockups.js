"use strict";
class MockupsView {
  constructor({ el, button, storage, getKey, onChange, notify, isSelected }) {
    Object.assign(this, {
      el,
      button,
      storage,
      getKey,
      onChange,
      notify,
      isSelected,
    });
    this.endpoint =
      "https://wqnrortftkffmbeugjky.supabase.co/functions/v1/ted-mockups";
    this.mockups = [];
    this.pins = [];
    this.loaded = false;
    this.loading = false;
    this.revision = 0;
    this.drafts = new Map();
    this.busy = new Set();
    this.filter = "All projects";
    this.error = "";
    this.owner = "";
    this.dialog = el("dialog", "mockup-dialog");
    this.dialog.setAttribute("aria-labelledby", "mockup-dialog-title");
    document.body.append(this.dialog);
    this.dialog.addEventListener("keydown", (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey ||
          e.target.closest('input, textarea, select, [contenteditable="true"]')) return;
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        this.navigate(e.key === "ArrowLeft" ? -1 : 1);
      }
    });
    this.dialog.addEventListener("cancel", (e) => {
      e.preventDefault();
      this.close();
    });
    this.dialog.addEventListener("close", () => {
      if (this.dialog.open) return;
      clearTimeout(this.tapTimer);
      this.resizeViewer?.disconnect();
      this.active = null;
      document.body.style.overflow = "";
    });
  }
  marker(pin) {
    const ted = pin.thread.filter((m) => m.who === "ted");
    const last = ted.at(-1);
    return last ? JSON.stringify([ted.length, last.at, last.text]) : "";
  }
  unread(pin) {
    const marker = this.marker(pin);
    return !!marker && this.storage.get("ted-mockup-read:" + pin.id) !== marker;
  }
  unreadCount() {
    return this.mockups.filter((m) => m.status !== "archived" && this.storage.get("ted-mockup-seen:" + m.id) !== (m.created_at || m.id)).length + this.pins.filter((p) => this.unread(p)).length;
  }
  hasUnread() {
    return this.unreadCount() > 0;
  }
  reset() {
    this.revision++;
    this.mockups = [];
    this.pins = [];
    this.loaded = false;
    this.error = "";
    this.owner = this.getKey();
    this.drafts.clear();
    this.close();
  }
  async api(method, body) {
    const controller = new AbortController(),
      timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const r = await fetch(
        this.endpoint +
          (method === "GET" ? "?key=" + encodeURIComponent(this.getKey()) : ""),
        {
          method,
          headers: method === "GET" ? {} : { "Content-Type": "text/plain" },
          body: body
            ? JSON.stringify({ key: this.getKey(), ...body })
            : undefined,
          cache: "no-store",
          referrerPolicy: "no-referrer",
          signal: controller.signal,
        },
      );
      let data;
      try {
        data = await r.json();
      } catch {
        throw Error("Unreadable response. Refresh to try again.");
      }
      if (!r.ok) {
        throw Error(
          r.status === 403
            ? "Access key not accepted. Use Access to reopen your private link."
            : data.error || "Could not save. Try again.",
        );
      }
      return data;
    } catch (e) {
      if (e.name === "AbortError") {
        throw Error(
          "Connection timed out. Refresh to check whether your feedback arrived.",
        );
      }
      if (e instanceof TypeError) {
        throw Error("Could not connect. Check your connection and try again.");
      }
      throw e;
    } finally {
      clearTimeout(timeout);
    }
  }
  async load() {
    if (!this.getKey() || this.loading) return;
    if (this.owner !== this.getKey()) this.reset();
    this.loading = true;
    this.error = "";
    const rev = this.revision, key = this.getKey();
    this.onChange();
    try {
      const data = await this.api("GET");
      if (!Array.isArray(data.mockups) || !Array.isArray(data.pins)) {
        throw Error("Could not read mockups. Refresh to try again.");
      }
      if (rev !== this.revision || key !== this.getKey()) return;
      this.mockups = data.mockups;
      this.pins = data.pins.map((p) => ({
        ...p,
        x: p.x ?? p.x_pct / 100,
        y: p.y ?? p.y_pct / 100,
        thread: (Array.isArray(p.thread) ? p.thread : []).filter((m) =>
          m && ["seb", "ted"].includes(m.who) && typeof m.text === "string"
        ),
      }));
      this.loaded = true;
      if (this.active) {
        const m = this.mockups.find((m) => m.id === this.active.id);
        if (m) {
          this.active = m;
          this.updateNavigation();
          this.drawPins();
          this.drawPanel();
          this.layoutViewer();
        } else this.close();
      }
    } catch (e) {
      this.error = e.message;
      if (this.isSelected()) this.notify(e.message, true);
    } finally {
      this.loading = false;
      this.onChange();
    }
  }
  imagePins(id) {
    return this.pins.filter((p) => p.mockup_id === id).sort((a, b) =>
      a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id)
    );
  }
  dot() {
    const dot = this.el("span", "reply-dot");
    dot.setAttribute("role", "img");
    dot.setAttribute("aria-label", "Unread replies from Ted");
    return dot;
  }
  render(root) {
    const { el, button } = this, intro = el("div", "mockup-intro");
    intro.append(
      el("h2", null, "a place to point things out."),
      el(
        "p",
        null,
        "Swipe through a batch. Open an image, tap a detail, and tell me what you think.",
      ),
    );
    root.append(intro);
    if (!this.loaded) {
      root.append(
        el(
          "p",
          "loading",
          this.loading
            ? "Opening your mockups…"
            : this.error || "Mockups are ready to load.",
        ),
      );
      if (!this.loading) {
        root.append(button("Load mockups", "primary", () => this.load()));
      }
      return;
    }
    const filter = el("label", "mockup-filter", "Project");
    const select = el("select");
    select.setAttribute("aria-label", "Filter mockups by project");
    ["All projects", ...new Set(this.mockups.map((m) => m.project))].forEach(
      (p) => {
        const option = el("option", null, p);
        option.value = p;
        option.selected = p === this.filter;
        select.append(option);
      },
    );
    select.addEventListener("change", () => {
      this.filter = select.value;
      this.onChange();
    });
    filter.append(select);
    intro.append(filter);
    const batches = new Map();
    this.mockups.filter((m) =>
      m.status !== "archived" &&
      (this.filter === "All projects" || m.project === this.filter)
    ).forEach((m) => {
      const key = JSON.stringify([m.project, m.batch]);
      if (!batches.has(key)) {
        batches.set(key, {
          project: m.project,
          title: m.batch,
          at: m.created_at,
          images: [],
        });
      }
      const batch = batches.get(key);
      batch.images.push(m);
      if (m.created_at > batch.at) batch.at = m.created_at;
    });
    if (!batches.size) {
      const empty = el("div", "state");
      empty.append(
        el("h3", null, "Room for the next idea."),
        el("p", null, "Ted will add the next batch here."),
      );
      root.append(empty);
      return;
    }
    [...batches.values()].sort((a, b) => b.at.localeCompare(a.at)).forEach(
      (batch) => {
        const section = el("section", "mockup-batch"),
          head = el("div", "mockup-batch-head"),
          text = el("div");
        text.append(
          el("h2", null, batch.title),
          el(
            "p",
            null,
            batch.project + " · " + batch.images.length +
              (batch.images.length === 1 ? " image" : " images"),
          ),
        );
        head.append(text);
        section.append(head);
        const row = el("div", "mockup-row");
        row.setAttribute("aria-label", batch.title + " images");
        row.tabIndex = 0;
        batch.images.sort((a, b) => this.imageOrder(a, b))
          .forEach((m) => row.append(this.card(m)));
        section.append(row);
        root.append(section);
      },
    );
  }
  card(m) {
    const { el, button } = this,
      pins = this.imagePins(m.id),
      card = el("article", "mockup-card");
    card.dataset.mockupId = m.id;
    const head = el("div", "mockup-card-head");
    head.append(el("h3", null, m.title));
    if (pins.some((p) => this.unread(p))) head.append(this.dot());
    card.append(head);
    const preview = el("div", "mockup-preview"),
      open = button("", "mockup-open", () => this.open(m));
    open.setAttribute("aria-label", "Open " + m.title);
    const img = el("img");
    img.src = this.imageURL(m.preview_url || m.image_url);
    img.alt = m.title;
    img.width = m.width;
    img.height = m.height;
    img.loading = "lazy";
    img.referrerPolicy = "no-referrer";
    open.append(img);
    preview.append(open);
    const overlay = el("div", "mockup-preview-pins");
    preview.append(overlay);
    const fitOverlay = () => {
      const width = preview.clientWidth,
        height = img.clientHeight,
        ratio = m.width / m.height;
      const w = Math.min(width, height * ratio);
      overlay.style.cssText = `width:${w}px;height:${w / ratio}px;left:${
        (width - w) / 2
      }px;top:0;`;
    };
    img.addEventListener("load", fitOverlay);
    new ResizeObserver(fitOverlay).observe(img);
    img.addEventListener("error", () => {
      preview.replaceChildren(
        el("p", "mockup-failed", "Image could not load. Refresh to try again."),
      );
    });
    pins.forEach((p, i) =>
      overlay.append(this.pinButton(p, i, () => this.open(m, p.id)))
    );
    card.append(preview);
    const foot = el("div", "mockup-card-foot"),
      n = pins.filter((p) => !p.resolved).length;
    foot.append(
      el(
        "span",
        "mockup-feedback-count",
        n + " open " + (n === 1 ? "pin" : "pins"),
      ),
    );
    if (m.status === "picked") {
      foot.append(el("span", "mockup-picked", "✓ Picked"));
    } else {
      const pick = button(
        "Pick this one",
        "",
        () => this.save({ action: "pick", mockup_id: m.id }, m.id),
      );
      pick.disabled = this.busy.has(m.id);
      foot.append(pick);
    }
    card.append(foot);
    return card;
  }
  imageURL(raw) {
    try {
      const url = new URL(raw);
      return url.protocol === "https:" || url.protocol === "http:"
        ? url.href
        : "";
    } catch {
      return "";
    }
  }
  pinButton(pin, index, onClick) {
    const b = this.button(
      "",
      "mockup-pin" + (pin.resolved ? " resolved" : ""),
      onClick,
    );
    b.style.left = ((pin.x ?? pin.x_pct / 100) * 100) + "%";
    b.style.top = ((pin.y ?? pin.y_pct / 100) * 100) + "%";
    b.setAttribute(
      "aria-label",
      "Pin " + (index + 1) + (pin.resolved ? ", resolved" : ""),
    );
    b.setAttribute("aria-pressed", String(this.selected === pin.id));
    b.append(this.el("span", null, index + 1));
    return b;
  }
  imageOrder(a, b) {
    return a.sort - b.sort || a.created_at.localeCompare(b.created_at) ||
      a.id.localeCompare(b.id);
  }
  groupImages(m) {
    return this.mockups.filter((image) => image.status !== "archived" &&
      image.project === m.project && image.batch === m.batch)
      .sort((a, b) => this.imageOrder(a, b));
  }
  navigate(direction) {
    if (!this.active || this.busy.has(this.active.id)) return;
    const group = this.groupImages(this.active),
      index = group.findIndex((m) => m.id === this.active.id),
      next = group[index + direction];
    if (index < 0 || !next) return;
    const focusInViewer = this.dialog.contains(document.activeElement);
    this.open(next);
    if (focusInViewer) this.viewport.focus({preventScroll: true});
  }
  updateNavigation() {
    const group = this.groupImages(this.active),
      index = group.findIndex((m) => m.id === this.active.id);
    this.positionLabel.textContent = index < 0 ? "Image outside this batch" : `${index + 1} of ${group.length}`;
    this.prevButton.hidden = index < 0;
    this.nextButton.hidden = index < 0;
    this.prevButton.disabled = index <= 0;
    this.nextButton.disabled = index < 0 || index >= group.length - 1;
    this.neighbourPreloads = [group[index - 1], group[index + 1]].filter(Boolean).map((m) => {
      const image = new Image();
      image.referrerPolicy = "no-referrer";
      image.src = this.imageURL(m.preview_url || m.image_url);
      return image;
    });
  }
  open(m, pinId = null) {
    this.storage.set("ted-mockup-seen:" + m.id, m.created_at || m.id);
    this.active = m;
    this.selected = pinId;
    this.pinMode = false;
    this.pending = null;
    clearTimeout(this.tapTimer);
    this.resizeViewer?.disconnect();
    this.zoom = 1; this.fitZoom = 1; this.fitting = true;
    this.panX = 0; this.panY = 0; this.baseWidth = 0; this.baseHeight = 0;
    this.fullLoading = false; this.fullLoaded = false; this.fullRetryAt = 0; this.lastTap = null;
    this.pointers = new Map();
    this.gesture = null;
    this.dialog.replaceChildren();
    const { el, button } = this,
      head = el("div", "mockup-dialog-head"),
      title = el("div"),
      h = el("h2", null, m.title);
    h.id = "mockup-dialog-title";
    this.positionLabel = el("p", "mockup-position");
    this.positionLabel.setAttribute("aria-live", "polite");
    title.append(h, el("p", null, m.project + " · " + m.batch), this.positionLabel);
    head.append(title, button("Close", "", () => this.close()));
    head.lastChild.setAttribute("aria-label", "Close mockup");
    this.dialog.append(head);
    const tools = el("div", "mockup-tools");
    tools.append(
      button("−", "", () => this.setZoom(this.zoom / 1.5)),
      button("100%", "mockup-scale", () => this.resetFit()),
      button("+", "", () => this.setZoom(this.zoom * 1.5)),
      button("Fit", "", () => this.resetFit()),
      button("Add pin", "mockup-add", () => { this.pinMode = true; this.centerPin(); }),
    );
    ["Zoom out", "Reset zoom to fit", "Zoom in", "Fit image"].forEach((label, i) =>
      tools.children[i].setAttribute("aria-label", label)
    );
    this.zoomLabel = tools.children[1];
    this.dialog.append(
      tools,
      el(
        "p",
        "mockup-hint",
        "Pinch to zoom, drag to pan, or swipe to change images. Use Add pin to leave feedback.",
      ),
    );
    this.index = el("div", "mockup-pin-index");
    this.dialog.append(this.index);
    this.viewport = el("div", "mockup-viewport");
    this.viewport.setAttribute("aria-label", "Zoomable mockup");
    this.viewport.tabIndex = 0;
    this.canvas = el("div", "mockup-canvas");
    const img = el("img");
    img.src = this.imageURL(m.preview_url || m.image_url);
    img.alt = m.title;
    img.draggable = false;
    img.referrerPolicy = "no-referrer";
    this.canvas.append(img);
    this.prevButton = button("‹", "mockup-nav mockup-prev", () => this.navigate(-1));
    this.nextButton = button("›", "mockup-nav mockup-next", () => this.navigate(1));
    this.prevButton.setAttribute("aria-label", "Previous image");
    this.nextButton.setAttribute("aria-label", "Next image");
    this.viewport.append(this.canvas, this.prevButton, this.nextButton);
    this.updateNavigation();
    this.dialog.append(this.viewport);
    this.dialogStatus = el("p", "mockup-status mockup-dialog-status");
    this.dialogStatus.setAttribute("role", "status");
    this.dialog.append(this.dialogStatus);
    this.panel = el("section", "mockup-panel");
    this.dialog.append(this.panel);
    this.installPointers();
    if (!this.dialog.open) this.dialog.showModal();
    document.body.style.overflow = "hidden";
    this.drawPins();
    this.drawPanel();
    this.layoutViewer();
    this.resizeViewer = new ResizeObserver(() => this.layoutViewer());
    this.resizeViewer.observe(this.viewport);
    this.onChange();
    const currentCanvas = this.canvas;
    img.addEventListener("error", () => {
      if (!this.active || this.canvas !== currentCanvas) return;
      this.dialogStatus.textContent =
        "Image could not load. Close and refresh to try again.";
    });
  }
  close() {
    if (this.active && this.busy.has(this.active.id)) return;
    clearTimeout(this.tapTimer);
    this.lastTap = null;
    this.resizeViewer?.disconnect();
    if (this.dialog.open) this.dialog.close();
    this.active = null;
    document.body.style.overflow = "";
    this.onChange();
  }
  layoutViewer() {
    if (!this.active) return;
    const v = this.viewport, m = this.active;
    const width = m.full_width || m.width, height = m.full_height || m.height;
    const oldW = this.baseWidth, oldH = this.baseHeight;
    const cx = oldW ? (this.lastWidth / 2 - this.panX) / (oldW * this.zoom) : .5;
    const cy = oldH ? (this.lastHeight / 2 - this.panY) / (oldH * this.zoom) : .5;
    this.baseWidth = width; this.baseHeight = height;
    this.fitZoom = Math.min(Math.max(1, v.clientWidth - 32) / width,
      Math.max(1, v.clientHeight - 32) / height, 10);
    this.minZoom = Math.min(.25, this.fitZoom / 4);
    this.lastWidth = v.clientWidth; this.lastHeight = v.clientHeight;
    if (this.fitting) { this.zoom = this.fitZoom; }
    else this.zoom = Math.max(this.minZoom, this.zoom);
    this.panX = v.clientWidth / 2 - cx * width * this.zoom;
    this.panY = v.clientHeight / 2 - cy * height * this.zoom;
    this.applyTransform();
  }
  resetFit() {
    this.setZoom(this.fitZoom);
  }
  applyTransform() {
    const v = this.viewport, w = this.baseWidth * this.zoom, h = this.baseHeight * this.zoom;
    const clamp = (p, size, available) => size <= available ? (available - size) / 2 : Math.max(available - size, Math.min(0, p));
    this.panX = clamp(this.panX, w, v.clientWidth);
    this.panY = clamp(this.panY, h, v.clientHeight);
    this.canvas.style.width = this.baseWidth + 'px';
    this.canvas.style.height = this.baseHeight + 'px';
    this.canvas.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`;
    this.canvas.style.setProperty('--mockup-zoom', this.zoom);
    this.zoomLabel.textContent = (Math.round(this.zoom * 1000) / 10) + '%';
    this.zoomLabel.title = 'Actual image scale. Reset to fit';
    this.viewport.dataset.zoom = this.zoom;
  }
  setZoom(value, anchor = null, panDelta = null) {
    if (!this.active) return;
    const old = this.zoom || this.fitZoom, next = Math.max(this.minZoom, Math.min(10, value));
    const x = anchor?.x ?? this.viewport.clientWidth / 2, y = anchor?.y ?? this.viewport.clientHeight / 2;
    this.panX = x - (x - this.panX) * next / old;
    this.panY = y - (y - this.panY) * next / old;
    this.zoom = next;
    this.fitting = Math.abs(next - this.fitZoom) < 1e-9;
    if (panDelta) {this.panX += panDelta.x;this.panY += panDelta.y;}
    this.applyTransform();
    const previewWidth = this.active.preview_width || this.active.width;
    if (next > this.fitZoom * 1.5 &&
        next * this.baseWidth * (window.devicePixelRatio || 1) > previewWidth) this.loadFull();
  }
  loadFull() {
    const m = this.active, canvas = this.canvas, url = this.imageURL(m?.full_url);
    if (!url || this.fullLoading || this.fullLoaded || Date.now() < this.fullRetryAt) return;
    this.fullLoading = true;
    this.dialogStatus.textContent = 'Loading full detail…';
    const image = new Image(); image.referrerPolicy = 'no-referrer';
    image.onload = async () => {
      try {await image.decode();} catch {}
      if (!this.active || this.canvas !== canvas) return;
      this.fullLoading = false; this.fullLoaded = true;
      this.canvas.querySelector('img').src = url;
      this.dialogStatus.textContent = 'Full detail loaded';
    };
    image.onerror = () => {
      if (!this.active || this.canvas !== canvas) return;
      this.fullLoading = false; this.fullRetryAt = Date.now() + 1500;
      this.dialogStatus.textContent = 'Full detail could not load. Zoom again to retry.';
    };
    image.src = url;
  }
  installPointers() {
    const v = this.viewport, point = e => ({x:e.clientX,y:e.clientY});
    const pair = () => {
      const [a,b] = [...this.pointers.values()];
      const r = v.getBoundingClientRect();
      return {x:(a.x+b.x)/2-r.left,y:(a.y+b.y)/2-r.top,d:Math.hypot(a.x-b.x,a.y-b.y)};
    };
    v.addEventListener('keydown', e => {
      if (e.target !== v || e.ctrlKey || e.metaKey || e.altKey) return;
      const r = (e.shiftKey ? {ArrowLeft:[60,0],ArrowRight:[-60,0],ArrowUp:[0,60],ArrowDown:[0,-60]} : {ArrowUp:[0,60],ArrowDown:[0,-60]})[e.key];
      if (r) {e.preventDefault();e.stopPropagation();this.panX += r[0];this.panY += r[1];this.applyTransform();}
      else if (['+','=','-','0','Home'].includes(e.key)) {
        e.preventDefault();this.setZoom(['0','Home'].includes(e.key) ? this.fitZoom : this.zoom * (e.key === '-' ? 1 / 1.5 : 1.5));
      }
    });
    v.addEventListener('wheel', e => {
      // Ctrl-wheel is browser page zoom (including trackpad pinch); leave it alone.
      if (e.ctrlKey || e.metaKey) return;
      e.preventDefault();
      const r = v.getBoundingClientRect();
      this.setZoom(this.zoom * Math.exp(-e.deltaY * (e.deltaMode === 1 ? .04 : .002)), {x:e.clientX-r.left,y:e.clientY-r.top});
    }, {passive:false});
    v.addEventListener('pointerdown', e => {
      if (e.target.closest('button') || e.button > 0 || this.pointers.size >= 2) return;
      this.pointers.set(e.pointerId,point(e));
      try {v.setPointerCapture(e.pointerId);} catch {}
      if (this.pointers.size === 1) this.gesture = {start:point(e),last:point(e),moved:false,multi:false,touch:e.pointerType === "touch",swipe:this.zoom <= this.fitZoom * 1.001,at:Date.now()};
      if (this.pointers.size === 2) {
        clearTimeout(this.tapTimer); this.lastTap = null;
        this.gesture.multi = true; this.gesture.pair = pair();
      }
    });
    v.addEventListener('pointermove', e => {
      if (!this.pointers.has(e.pointerId) || !this.gesture) return;
      this.pointers.set(e.pointerId,point(e));
      const g = this.gesture;
      if (this.pointers.size === 2) {
        const now = pair(), old = g.pair;
        this.setZoom(this.zoom * now.d / Math.max(1,old.d), old, {x:now.x-old.x,y:now.y-old.y});
        g.pair = now; g.moved = true;
      } else {
        if (Math.hypot(e.clientX-g.start.x,e.clientY-g.start.y) > 8) g.moved = true;
        if (g.moved || g.multi) {
          this.panX += e.clientX-g.last.x; this.panY += e.clientY-g.last.y; this.applyTransform();
        }
        g.last = point(e);
      }
    });
    const finish = (e,cancel=false) => {
      if (!this.pointers.has(e.pointerId)) return;
      const g = this.gesture; this.pointers.delete(e.pointerId);
      if (!this.pointers.size) {
        const dx = g ? e.clientX - g.start.x : 0, dy = g ? e.clientY - g.start.y : 0;
        if (g && !g.multi && !cancel && g.touch && g.swipe &&
            this.zoom <= this.fitZoom * 1.001 && Math.abs(dx) >= 50 &&
            Math.abs(dx) > Math.abs(dy) * 1.5 && Date.now() - g.at < 1000) {
          clearTimeout(this.tapTimer); this.lastTap = null;
          this.navigate(dx < 0 ? 1 : -1);
        } else if (g && !g.moved && !g.multi && !cancel) {
          const now = Date.now(), last = this.lastTap;
          if (last && now-last.at < 320 && Math.hypot(e.clientX-last.x,e.clientY-last.y)<28) {
            clearTimeout(this.tapTimer); this.lastTap = null;
            const r = v.getBoundingClientRect(); this.setZoom(this.fitting ? this.fitZoom * 2.5 : this.fitZoom,{x:e.clientX-r.left,y:e.clientY-r.top});
          } else {
            clearTimeout(this.tapTimer);
            this.lastTap = {at:now,...point(e)};
            const r = this.canvas.getBoundingClientRect(), x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;
            this.tapTimer = setTimeout(() => {
              this.lastTap = null;
              if (this.active && this.pinMode && x>=0 && x<=1 && y>=0 && y<=1) this.newPin(x,y);
            },320);
          }
        }
        this.gesture = null;
      } else if (g) {g.last=[...this.pointers.values()][0];g.start=g.last;g.moved=true;}
      if (cancel) {clearTimeout(this.tapTimer);this.lastTap=null;}
    };
    v.addEventListener('pointerup',e=>finish(e));
    v.addEventListener('pointercancel',e=>finish(e,true));
    v.addEventListener('lostpointercapture',e=>finish(e,true));
  }
  centerPin() {
    const v = this.viewport.getBoundingClientRect(), c = this.canvas.getBoundingClientRect();
    this.newPin(Math.max(0,Math.min(1,(v.left+v.width/2-c.left)/c.width)),Math.max(0,Math.min(1,(v.top+v.height/2-c.top)/c.height)));
  }
  newPin(x, y) {
    if (this.busy.has(this.active.id) || this.active.status === "archived") {
      return;
    }
    this.pending = {
      x: Math.max(0, Math.min(1, Number(x.toFixed(6)))),
      y: Math.max(0, Math.min(1, Number(y.toFixed(6)))),
    };
    this.selected = null;
    this.drawPins();
    this.drawPanel();
    this.panel.querySelector("textarea")?.focus();
  }
  drawPins() {
    if (!this.active) return;
    this.canvas.querySelectorAll("button").forEach((b) => b.remove());
    this.index.replaceChildren();
    this.imagePins(this.active.id).forEach((p, i) => {
      const select = () => {
        if (this.busy.has(this.active.id)) return;
        this.selected = p.id;
        this.pending = null;
        this.pinMode = false;
        this.drawPins();
        this.drawPanel();
      };
      this.canvas.append(this.pinButton(p, i, select));
      const b = this.button(
        "Pin " + (i + 1) + (p.resolved ? " ✓" : ""),
        "",
        select,
      );
      b.setAttribute("aria-pressed", String(this.selected === p.id));
      if (this.unread(p)) b.append(this.dot());
      this.index.append(b);
    });
    if (this.pending) {
      this.canvas.append(
        this.pinButton(
          { ...this.pending, resolved: false, id: "draft" },
          this.imagePins(this.active.id).length,
          () => this.panel.querySelector("textarea")?.focus(),
        ),
      );
    }
  }
  draftKey() {
    return this.selected || this.active.id + ":new";
  }
  drawPanel() {
    if (!this.active) return;
    const { el, button } = this,
      all = this.imagePins(this.active.id),
      pin = all.find((p) => p.id === this.selected);
    this.panel.replaceChildren();
    this.panel.hidden = !pin && !this.pending;
    if (this.panel.hidden) return;
    const head = el("div", "mockup-panel-head");
    head.append(
      el(
        "h3",
        null,
        pin
          ? "Pin " + (all.indexOf(pin) + 1) +
            (pin.resolved ? " · Resolved" : "")
          : "New pin",
      ),
      button("Close thread", "quiet", () => {
        if (this.busy.has(this.active.id)) return;
        this.selected = null;
        this.pending = null;
        this.pinMode = false;
        this.drawPins();
        this.drawPanel();
      }),
    );
    this.panel.append(head);
    if (pin) {
      this.storage.set("ted-mockup-read:" + pin.id, this.marker(pin));
      const messages = el("ol", "messages");
      pin.thread.forEach((m) => {
        const li = el("li", "message message-" + m.who);
        li.setAttribute("aria-label", m.who === "ted" ? "Ted" : "Sebastian");
        if (m.who === "ted") li.append(el("span", "message-label", "ted"));
        li.append(el("p", null, m.text));
        const date = new Date(m.at);
        if (!Number.isNaN(+date)) {
          const time = el(
            "time",
            null,
            date.toLocaleString([], {
              month: "short",
              day: "numeric",
              hour: "numeric",
              minute: "2-digit",
            }),
          );
          time.dateTime = date.toISOString();
          li.append(time);
        }
        messages.append(li);
      });
      this.panel.append(messages);
      messages.scrollTop = messages.scrollHeight;
      this.onRead?.();
    }
    const form = el("form", "mockup-comment-form"), input = el("textarea");
    input.setAttribute(
      "aria-label",
      pin ? "Reply to pin " + (all.indexOf(pin) + 1) : "Comment for Ted",
    );
    input.placeholder = pin ? "Reply to this pin…" : "What should change here?";
    input.maxLength = 1200;
    input.rows = 2;
    const draftKey = this.draftKey();
    input.value = this.drafts.get(draftKey) || "";
    input.addEventListener(
      "input",
      () => this.drafts.set(draftKey, input.value),
    );
    const send = button(
      pin ? "Send reply" : "Send comment",
      "primary",
      () => {},
    );
    send.type = "submit";
    form.append(input, send);
    this.panel.append(form);
    this.panelStatus = el("p", "mockup-status");
    this.panelStatus.setAttribute("role", "status");
    this.panelStatus.setAttribute("aria-live", "polite");
    this.panel.append(this.panelStatus);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!input.value.trim()) {
        this.panelStatus.textContent = "Write a comment first.";
        input.focus();
        return;
      }
      const body = pin
        ? { action: "reply", pin_id: pin.id, text: input.value.trim() }
        : {
          action: "pin",
          mockup_id: this.active.id,
          ...this.pending,
          text: input.value.trim(),
        };
      await this.save(body, this.active.id, draftKey);
    });
    if (this.busy.has(this.active.id)) {
      this.panel.querySelectorAll("button,textarea").forEach((e) =>
        e.disabled = true
      );
    }
  }
  async save(body, id, draftKey = null) {
    if (this.busy.has(id)) return;
    this.busy.add(id);
    const owner = this.getKey();
    if (this.active) {
      this.dialog.querySelectorAll("button,textarea").forEach((e) =>
        e.disabled = true
      );
      if (this.panelStatus) this.panelStatus.textContent = "Sending to Ted…";
    }
    this.onChange();
    try {
      const data = await this.api("POST", body);
      if (!data.ok || (body.action === "pick" ? !data.mockup : !data.pin)) {
        throw Error("Save was not confirmed. Refresh to check your feedback.");
      }
      if (owner !== this.getKey()) return;
      this.revision++;
      if (data.mockup) {
        const i = this.mockups.findIndex((m) => m.id === data.mockup.id);
        if (i >= 0) this.mockups[i] = data.mockup;
      }
      if (data.pin) {
        const i = this.pins.findIndex((p) => p.id === data.pin.id);
        if (i >= 0) this.pins[i] = data.pin;
        else this.pins.push(data.pin);
        if (this.active?.id === id) {
          this.selected = data.pin.id;
          this.pending = null;
          this.pinMode = false;
        }
      }
      if (draftKey) this.drafts.delete(draftKey);
      if (this.active?.id === id) {
        this.drawPins();
        this.drawPanel();
        this.panelStatus.textContent = "Sent to Ted.";
      }
      this.notify(
        body.action === "pick"
          ? "Picked. Ted has your choice."
          : "Sent to Ted.",
      );
    } catch (e) {
      if (this.active?.id === id) {
        const target = this.panel.hidden ? this.dialogStatus : this.panelStatus;
        target.textContent = e.message;
      }
      this.notify(e.message, true);
    } finally {
      this.busy.delete(id);
      if (this.active) {
        this.dialog.querySelectorAll("button,textarea").forEach((e) =>
          e.disabled = false
        );
        this.updateNavigation();
      }
      this.onChange();
    }
  }
}
window.MockupsView = MockupsView;
