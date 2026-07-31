// Collaborative editor hook: CodeMirror 6 + @codemirror/collab, with the
// LiveView process as the central authority.
//
// The CodeMirror modules themselves are loaded with dynamic import() when the hook mounts.

window.Hooks = window.Hooks ?? {};

const CM_MODULES = {
  state: "https://esm.sh/@codemirror/state@6",
  view: "https://esm.sh/@codemirror/view@6",
  commands: "https://esm.sh/@codemirror/commands@6",
  collab: "https://esm.sh/@codemirror/collab@6",
};

const PUSH_THROTTLE_MS = 60;
const CURSOR_TTL_MS = 10000;

window.Hooks.CollabEditor = {
  mounted() {
    // Events can arrive between mount and the (async) editor init finishing;
    // queue them and drain once ready.
    this.queue = [];
    this.ready = false;
    const gate = (type) => (payload) => {
      if (this.ready) this.dispatch(type, payload);
      else this.queue.push([type, payload]);
    };

    this.handleEvent("init", (payload) => this.initEditor(payload));
    this.handleEvent("updates", gate("updates"));
    this.handleEvent("cursor", gate("cursor"));
    this.handleEvent("editor_left", gate("editor_left"));
    this.handleEvent("limit_exceeded", gate("limit_exceeded"));
    this.handleEvent("editor_error", gate("editor_error"));
    this.handleEvent("resync", gate("resync"));
    this.handleEvent("expired", gate("expired"));

    // Ask the server for the current doc rather than reading it from the
    // DOM — the DOM inside phx-update="ignore" can be stale.
    this.pushEvent("request_init", {});
  },

  destroyed() {
    if (this.pushTimer) clearTimeout(this.pushTimer);
    if (this.pruneTimer) clearInterval(this.pruneTimer);
    if (this.view) this.view.destroy();
  },

  async initEditor(init) {
    const [state, view, commands, collab] = await Promise.all(
      Object.values(CM_MODULES).map((url) => import(url))
    );
    // Stash what the event handlers need.
    this.cm = { state, view, collab };
    this.clientId = init.clientId;
    this.maxBytes = init.maxBytes;

    const documentSizeLimit = state.EditorState.changeFilter.of((tr) => {
      if (!tr.docChanged) return true;
      if (new TextEncoder().encode(tr.newDoc.toString()).byteLength <= this.maxBytes) {
        return true;
      }
      queueMicrotask(() =>
        this.showNotice("This temporary document has reached its 64 KiB limit.")
      );
      return false;
    });

    // ---- Remote cursors: a StateField of clientId -> cursor info. ----
    // Positions are mapped through every local document change, so cursors
    // ride along correctly between broadcasts.
    const setCursor = state.StateEffect.define();
    const removeCursor = state.StateEffect.define();
    this.setCursor = setCursor;
    this.removeCursor = removeCursor;

    class CaretWidget extends view.WidgetType {
      constructor(name, color) {
        super();
        this.name = name;
        this.color = color;
      }
      eq(other) {
        return other.name === this.name && other.color === this.color;
      }
      toDOM() {
        const caret = document.createElement("span");
        caret.className = "remote-caret";
        caret.style.borderLeftColor = this.color;
        const label = document.createElement("span");
        label.className = "remote-caret-label";
        label.style.backgroundColor = this.color;
        label.textContent = this.name;
        caret.appendChild(label);
        return caret;
      }
      ignoreEvent() {
        return true;
      }
    }

    const cursorsToDecorations = (cursors) => {
      const ranges = [];
      for (const c of cursors.values()) {
        const from = Math.min(c.anchor, c.head);
        const to = Math.max(c.anchor, c.head);
        if (to > from) {
          ranges.push(
            view.Decoration.mark({
              class: "remote-selection",
              attributes: { style: `background-color: ${c.color}2e;` },
            }).range(from, to)
          );
        }
        ranges.push(
          view.Decoration.widget({
            widget: new CaretWidget(c.name, c.color),
            side: -1,
          }).range(c.head)
        );
      }
      return view.Decoration.set(ranges, true);
    };

    const remoteCursors = state.StateField.define({
      create: () => new Map(),
      update(cursors, tr) {
        let next = cursors;
        const copy = () => (next === cursors ? (next = new Map(cursors)) : next);
        if (tr.docChanged) {
          copy();
          for (const [id, c] of next) {
            next.set(id, {
              ...c,
              anchor: tr.changes.mapPos(c.anchor),
              head: tr.changes.mapPos(c.head),
            });
          }
        }
        for (const effect of tr.effects) {
          if (effect.is(setCursor)) copy().set(effect.value.clientId, effect.value);
          if (effect.is(removeCursor)) copy().delete(effect.value.clientId);
        }
        return next;
      },
      provide: (field) => view.EditorView.decorations.from(field, cursorsToDecorations),
    });
    this.remoteCursors = remoteCursors;

    // ---- The editor itself. ----
    this.view = new view.EditorView({
      parent: this.el,
      state: state.EditorState.create({
        doc: init.doc,
        extensions: [
          view.lineNumbers(),
          view.highlightActiveLine(),
          view.drawSelection(),
          view.keymap.of(commands.defaultKeymap),
          collab.collab({
            startVersion: init.version,
            clientID: init.clientId,
          }),
          documentSizeLimit,
          remoteCursors,
          view.EditorView.updateListener.of((update) => {
            if (update.docChanged || update.selectionSet) this.schedulePush();
          }),
          view.EditorView.lineWrapping,
        ],
      }),
    });

    // Expire cursors we haven't heard from in a while (cursor broadcasts are
    // frequent, so a live peer refreshes its entry constantly).
    this.pruneTimer = setInterval(() => this.pruneCursors(), CURSOR_TTL_MS / 2);

    this.ready = true;
    for (const [type, payload] of this.queue) this.dispatch(type, payload);
    this.queue = [];
  },

  dispatch(type, payload) {
    if (type === "updates") this.applyUpdates(payload);
    else if (type === "cursor") this.applyCursor(payload);
    else if (type === "editor_left") this.dropCursor(payload.clientId);
    else if (type === "limit_exceeded") this.handleLimitExceeded(payload);
    else if (type === "editor_error") this.showNotice(payload.message);
    else if (type === "resync") this.resync();
    else if (type === "expired") this.expire();
  },

  // ---- Outbound: push pending updates + our cursor, throttled. ----

  schedulePush() {
    if (this.pushTimer) return;
    this.pushTimer = setTimeout(() => {
      this.pushTimer = null;
      this.pushNow();
    }, PUSH_THROTTLE_MS);
  },

  pushNow() {
    if (!this.ready) return;
    const { collab } = this.cm;
    const editorState = this.view.state;

    const updates = collab.sendableUpdates(editorState);
    if (updates.length) {
      this.pushEvent("push_updates", {
        version: collab.getSyncedVersion(editorState),
        updates: updates.map((u) => ({
          clientID: u.clientID,
          changes: u.changes.toJSON(),
        })),
      });
    }

    const { anchor, head } = editorState.selection.main;
    this.pushEvent("cursor", { anchor, head });
  },

  // ---- Inbound. ----

  applyUpdates({ from_version, updates }) {
    const { state, collab } = this.cm;
    const synced = collab.getSyncedVersion(this.view.state);

    // The broadcast stream and our init snapshot can overlap: drop the
    // prefix of any batch we've already incorporated.
    const skip = synced - from_version;
    if (skip < 0) {
      // A gap means we somehow missed a broadcast
      console.warn(`collab: update gap (synced ${synced}, got ${from_version})`);
      return;
    }
    if (skip >= updates.length) return;

    const toApply = updates.slice(skip).map((u) => ({
      clientID: u.clientID,
      changes: state.ChangeSet.fromJSON(u.changes),
    }));
    this.view.dispatch(collab.receiveUpdates(this.view.state, toApply));

    // If we had a push rejected, our pending updates were just rebased over
    // the incoming ones so send them again.
    if (collab.sendableUpdates(this.view.state).length) this.schedulePush();
  },

  applyCursor(payload) {
    const docLength = this.view.state.doc.length;
    const anchor = Math.max(0, Math.min(Number(payload.anchor) || 0, docLength));
    const head = Math.max(0, Math.min(Number(payload.head) || 0, docLength));
    this.view.dispatch({
      effects: this.setCursor.of({
        clientId: payload.clientId,
        name: payload.name,
        color: payload.color,
        anchor,
        head,
        seenAt: Date.now(),
      }),
    });
  },

  handleLimitExceeded(payload) {
    this.showNotice(payload.message);
    setTimeout(() => this.resync(), 1000);
  },

  showNotice(message) {
    const notice = document.getElementById("collab-editor-notice");
    if (!notice) return;
    notice.textContent = message;
    notice.className =
      "mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800";
  },

  resync() {
    if (this.reloading) return;
    this.reloading = true;
    window.location.reload();
  },

  expire() {
    if (this.pushTimer) clearTimeout(this.pushTimer);
    if (this.pruneTimer) clearInterval(this.pruneTimer);
    this.ready = false;
    if (this.view) {
      this.view.destroy();
      this.view = null;
    }
    this.el.replaceChildren();
    this.resync();
  },

  dropCursor(clientId) {
    this.view.dispatch({ effects: this.removeCursor.of({ clientId }) });
  },

  pruneCursors() {
    const cursors = this.view.state.field(this.remoteCursors);
    const now = Date.now();
    for (const [clientId, c] of cursors) {
      if (now - c.seenAt > CURSOR_TTL_MS) this.dropCursor(clientId);
    }
  },
};
