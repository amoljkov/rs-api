import json
import threading
import tkinter as tk
from tkinter import messagebox

import ttkbootstrap as tb
from tkinter import ttk

from rustore.config import get_settings
from rustore.token_manager import RuStoreTokenManager
from rustore.api_client import RuStoreApiClient
from rustore.methods import load_all, list_methods, MethodDef

from ui.widgets import make_scrolled_text_both, make_scrolled_treeview, ScrollFrame
from ui.clipboard import bind_clipboard_shortcuts, add_context_menu
from ui.tooltips import Tooltip
from ui.body_template import build_body_template, parse_typed
from ui.logger_adapter import UiLogger
from ui.layout import (
    LEFT_PANE_MINSIZE,
    PARAMS_PANE_MINSIZE,
    RESPONSE_PANE_MINSIZE,
    DEFAULT_GEOMETRY,
    BODY_TEXT_HEIGHT,
)


class MainWindow(tb.Window):
    def __init__(self):
        # Theme is intentionally hardcoded.
        # Available light themes you can try:
        # cosmo, flatly, journal, litera, lumen, minty, pulse, sandstone,
        # simplex, united, yeti, morph
        super().__init__(themename="flatly")

        self.title("RuStore Public API Client")
        self.geometry(DEFAULT_GEOMETRY)

        self.settings = get_settings()

        cfg = load_all("methods.yaml")
        self.methods: list[MethodDef] = list_methods(cfg)

        self.method_by_iid: dict[str, MethodDef] = {}

        self.env_var = tk.StringVar(value="prod")
        self.pretty_var = tk.BooleanVar(value=True)

        self.path_entries = {}
        self.query_entries = {}

        self._current_method_iid: str | None = None
        self._body_dirty: bool = False

        self._build_ui()

        ui_logger = UiLogger(self.log)
        self.tm = RuStoreTokenManager(self.settings, logger=ui_logger)
        self.client = RuStoreApiClient(self.settings, self.tm, logger=ui_logger)

        self._populate_methods_tree()
        self._on_method_change()

    # ---------------- logging ----------------
    def log(self, msg: str):
        self.logs_text.insert(tk.END, str(msg) + "\n")
        self.logs_text.see(tk.END)

    def _copy_text_widget_all(self, w: tk.Text):
        txt = w.get("1.0", tk.END).rstrip("\n")
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.status.config(text="Скопировано целиком в буфер обмена")

    # ---------------- UI build ----------------
    def _build_ui(self):
        root = ttk.PanedWindow(self, orient="horizontal")
        root.pack(fill="both", expand=True)

        # ========== Pane 1: request selection ==========
        pane_left = ttk.Frame(root, padding=(12, 12))
        root.add(pane_left, weight=1)
        try:
            root.paneconfig(pane_left, minsize=LEFT_PANE_MINSIZE)
        except Exception:
            pass

        ttk.Label(pane_left, text="Выбор запроса", font=("Segoe UI", 11, "bold")).pack(anchor="w")

        ttk.Label(pane_left, text="Окружение", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 0))
        env_box = ttk.Combobox(pane_left, textvariable=self.env_var, values=["prod", "sandbox"], state="readonly")
        env_box.pack(fill="x", pady=(6, 10))
        env_box.bind("<<ComboboxSelected>>", lambda e: self._on_method_change())

        ttk.Label(pane_left, text="Методы", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tree_frame, self.methods_tree = make_scrolled_treeview(pane_left)
        tree_frame.pack(fill="both", expand=True, pady=(6, 10))
        self.methods_tree.bind("<<TreeviewSelect>>", lambda e: self._on_tree_select())

        ttk.Button(pane_left, text="Обновить токен", bootstyle="secondary", command=self._force_refresh_token).pack(
            fill="x", pady=(0, 6)
        )

        # ========== Pane 2: request params (single compact block) ==========
        pane_params = ttk.Frame(root, padding=(12, 12))
        root.add(pane_params, weight=1)
        try:
            root.paneconfig(pane_params, minsize=PARAMS_PANE_MINSIZE)
        except Exception:
            pass

        # header (more noticeable)
        self.method_title = ttk.Label(pane_params, text="", font=("Segoe UI", 11, "bold"))
        self.method_title.pack(anchor="w")

        self.method_meta = ttk.Label(pane_params, text="", font=("Segoe UI", 10), justify="left")
        self.method_meta.pack(anchor="w", pady=(2, 0))

        # compact params area (scrollable)
        params_box = ttk.Labelframe(pane_params, text="Параметры запроса", padding=(10, 8))
        params_box.pack(fill="both", expand=True, pady=(10, 10))

        self.params_scroll = ScrollFrame(params_box)
        # IMPORTANT: ScrolledFrame add `.container` to pack/grid
        self.params_scroll.container.pack(fill="both", expand=True)

        # BODY (inside params block, but shown only when needed)
        self.body_label = ttk.Label(self.params_scroll.inner, text="BODY (JSON)", font=("Segoe UI", 10, "bold"))
        body_frame, self.body_text = make_scrolled_text_both(self.params_scroll.inner, wrap_mode="none")
        self.body_frame = body_frame
        self.body_text.configure(height=BODY_TEXT_HEIGHT)

        def on_body_modified(_e=None):
            self.body_text.edit_modified(False)
            self._body_dirty = True

        self.body_text.bind("<<Modified>>", on_body_modified, add=True)
        self.body_text.edit_modified(False)

        # call row
        call_row = ttk.Frame(pane_params)
        call_row.pack(fill="x")

        ttk.Button(call_row, text="Вызвать метод", bootstyle="primary", command=self._call_clicked).pack(side="left")
        ttk.Checkbutton(
            call_row,
            text="Pretty JSON",
            variable=self.pretty_var,
            bootstyle="round-toggle",
        ).pack(side="left", padx=14)

        # ========== Pane 3: response ==========
        pane_resp = ttk.Frame(root, padding=(12, 12))
        root.add(pane_resp, weight=4)
        try:
            root.paneconfig(pane_resp, minsize=RESPONSE_PANE_MINSIZE)
        except Exception:
            pass

        ttk.Label(pane_resp, text="Ответ", font=("Segoe UI", 11, "bold")).pack(anchor="w")

        resp_box = ttk.Labelframe(pane_resp, text="Ответ / Логи", padding=(10, 8))
        resp_box.pack(fill="both", expand=True, pady=(10, 10))

        # toolbar
        resp_toolbar = ttk.Frame(resp_box)
        resp_toolbar.pack(fill="x", pady=(0, 8))

        ttk.Button(
            resp_toolbar, text="Copy Pretty", bootstyle="secondary-outline",
            command=lambda: self._copy_text_widget_all(self.pretty_text)
        ).pack(side="right", padx=6)

        ttk.Button(
            resp_toolbar, text="Copy Raw", bootstyle="secondary-outline",
            command=lambda: self._copy_text_widget_all(self.raw_text)
        ).pack(side="right")

        ttk.Button(
            resp_toolbar, text="Copy Logs", bootstyle="secondary-outline",
            command=lambda: self._copy_text_widget_all(self.logs_text)
        ).pack(side="right", padx=6)

        ttk.Button(
            resp_toolbar, text="Clear Logs", bootstyle="secondary-outline",
            command=lambda: self.logs_text.delete("1.0", tk.END)
        ).pack(side="right")

        # response tabs inside right block (still in one main tab)
        self.resp_tabs = ttk.Notebook(resp_box)
        self.resp_tabs.pack(fill="both", expand=True)

        pretty_frame, self.pretty_text = make_scrolled_text_both(self.resp_tabs, wrap_mode="none")
        raw_frame, self.raw_text = make_scrolled_text_both(self.resp_tabs, wrap_mode="none")
        logs_frame, self.logs_text = make_scrolled_text_both(self.resp_tabs, wrap_mode="none")

        self.resp_tabs.add(pretty_frame, text="Pretty")
        self.resp_tabs.add(raw_frame, text="Raw")
        self.resp_tabs.add(logs_frame, text="Logs")

        # status bar
        self.status = ttk.Label(self, text="", anchor="w", foreground="#555")
        self.status.pack(fill="x", side="bottom")

    # ---------------- methods tree ----------------
    def _populate_methods_tree(self):
        self.methods_tree.delete(*self.methods_tree.get_children())
        self.method_by_iid.clear()

        grouped: dict[str, list[MethodDef]] = {}
        for m in self.methods:
            grouped.setdefault(m.group_title, []).append(m)

        for g in grouped:
            grouped[g].sort(key=lambda x: x.title)

        for gi, group_title in enumerate(sorted(grouped.keys())):
            group_iid = f"g:{gi}"
            self.methods_tree.insert("", "end", iid=group_iid, text=group_title, open=True)

            for mi, m in enumerate(grouped[group_title]):
                method_iid = f"m:{gi}:{mi}"
                self.methods_tree.insert(group_iid, "end", iid=method_iid, text=f"{m.title}  ({m.http_method})")
                self.method_by_iid[method_iid] = m

        root_groups = self.methods_tree.get_children("")
        if root_groups:
            first_group = root_groups[0]
            children = self.methods_tree.get_children(first_group)
            if children:
                self.methods_tree.selection_set(children[0])
                self.methods_tree.focus(children[0])

    def _on_tree_select(self):
        sel = self.methods_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid not in self.method_by_iid:
            self.methods_tree.selection_remove(iid)
            return
        self._on_method_change()

    def _selected_method(self) -> MethodDef | None:
        sel = self.methods_tree.selection()
        if not sel:
            return None
        return self.method_by_iid.get(sel[0])

    # ---------------- actions ----------------
    def _force_refresh_token(self):
        try:
            self.tm.get_token(force_refresh=True)
            messagebox.showinfo("OK", "Токен обновлён. См. вкладку Logs.")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _clear_container(self, frame: ttk.Frame):
        for w in frame.winfo_children():
            w.destroy()

    def _render_kv_section(self, parent: ttk.Frame, title: str, schema: dict, store: dict):
        """
        Render PATH or QUERY fields into parent as a compact section.
        Only called when schema is non-empty.
        """
        ttk.Label(parent, text=title, font=("Segoe UI", 10, "bold")).grid(
            row=self._grid_row, column=0, sticky="w", pady=(8, 6), columnspan=2
        )
        self._grid_row += 1

        for name, meta in (schema or {}).items():
            t = (meta.get("type") or "str")
            req = bool(meta.get("required", False))
            hint = (meta.get("hint") or "").strip()

            label = f"{name} ({t})" + (" *" if req else "")
            ttk.Label(parent, text=label).grid(row=self._grid_row, column=0, sticky="w", padx=(0, 10), pady=4)

            e = ttk.Entry(parent)
            e.grid(row=self._grid_row, column=1, sticky="ew", pady=4)
            parent.grid_columnconfigure(1, weight=1)

            bind_clipboard_shortcuts(e)
            add_context_menu(e)
            if hint:
                Tooltip(e, hint)

            store[name] = (e, meta)
            self._grid_row += 1

    def _on_method_change(self):
        m = self._selected_method()
        if not m:
            return

        env = self.env_var.get()
        path = (m.paths or {}).get(env, "")
        full = f"{self.settings.base_url}{path}"

        # Header in params pane: more noticeable
        self.method_title.config(text=m.title)
        self.method_meta.config(text=f"{m.http_method}  {path}\n{full}")

        # Rebuild params UI compactly
        self._clear_container(self.params_scroll.inner)
        self.path_entries.clear()
        self.query_entries.clear()

        self._grid_row = 0

        path_schema = (m.params.get("path") or {})
        query_schema = (m.params.get("query") or {})
        body_schema = (m.params.get("body") or {})

        has_path = bool(path_schema)
        has_query = bool(query_schema)
        has_body = bool(body_schema)

        if has_path:
            self._render_kv_section(self.params_scroll.inner, "PATH", path_schema, self.path_entries)

        if has_query:
            self._render_kv_section(self.params_scroll.inner, "QUERY", query_schema, self.query_entries)

        # Body section: show only when schema exists
        if has_body:
            ttk.Separator(self.params_scroll.inner).grid(row=self._grid_row, column=0, columnspan=2, sticky="ew", pady=(10, 10))
            self._grid_row += 1

            self.body_label = ttk.Label(self.params_scroll.inner, text="BODY (JSON)", font=("Segoe UI", 10, "bold"))
            self.body_label.grid(row=self._grid_row, column=0, sticky="w", pady=(0, 6), columnspan=2)
            self._grid_row += 1

            self.body_frame, self.body_text = make_scrolled_text_both(self.params_scroll.inner, wrap_mode="none")
            self.body_frame.grid(row=self._grid_row, column=0, columnspan=2, sticky="ew")
            self.body_text.configure(height=BODY_TEXT_HEIGHT)
            self.params_scroll.inner.grid_columnconfigure(1, weight=1)
            self._grid_row += 1

            # Track edits
            def on_body_modified(_e=None):
                self.body_text.edit_modified(False)
                self._body_dirty = True

            self.body_text.bind("<<Modified>>", on_body_modified, add=True)
            self.body_text.edit_modified(False)

            # Fill template only when switching method
            sel = self.methods_tree.selection()
            current_iid = sel[0] if sel else None
            method_changed = (current_iid != self._current_method_iid)
            if method_changed:
                self._current_method_iid = current_iid
                self._body_dirty = False

            if not self._body_dirty:
                template = build_body_template(body_schema)
                self.body_text.delete("1.0", tk.END)
                self.body_text.insert("1.0", json.dumps(template, ensure_ascii=False, indent=2))
                self.body_text.edit_modified(False)
        else:
            # no body for this method
            self._current_method_iid = self.methods_tree.selection()[0] if self.methods_tree.selection() else None
            self._body_dirty = False

        # Compact note for required
        if has_path or has_query:
            ttk.Label(self.params_scroll.inner, text="* обязательные", foreground="#666").grid(
                row=self._grid_row, column=0, sticky="w", pady=(10, 0), columnspan=2
            )
            self._grid_row += 1

        # Clear response panes
        self.pretty_text.delete("1.0", tk.END)
        self.raw_text.delete("1.0", tk.END)
        self.status.config(text="")

    def _collect_params(self, store: dict, section_name: str):
        values = {}
        missing = []
        for name, (entry, meta) in store.items():
            raw = entry.get().strip()
            t = meta.get("type", "str")
            req = meta.get("required", False)

            if req and raw == "":
                missing.append(f"{section_name}.{name}")
                continue
            if raw == "":
                values[name] = None
                continue

            try:
                values[name] = parse_typed(raw, t)
            except Exception as e:
                raise ValueError(f"{section_name}.{name}: не удалось привести '{raw}' к {t}: {e}") from e

        return values, missing

    def _call_clicked(self):
        m = self._selected_method()
        if not m:
            return

        env = self.env_var.get()
        path_template = (m.paths or {}).get(env)
        if not path_template:
            messagebox.showerror("Ошибка", f"Для окружения '{env}' не задан путь в methods.yaml")
            return

        try:
            path_params, miss1 = self._collect_params(self.path_entries, "path")
            query_params, miss2 = self._collect_params(self.query_entries, "query")
        except Exception as e:
            messagebox.showerror("Ошибка в параметрах", str(e))
            return

        missing = miss1 + miss2
        if missing:
            messagebox.showerror("Не заполнено", "Обязательные поля:\n" + "\n".join(missing))
            return

        body = None
        # if body editor exists for this method, read it
        if hasattr(self, "body_text") and self.body_text.winfo_exists():
            body_raw = self.body_text.get("1.0", tk.END).strip()
            if body_raw:
                try:
                    body = json.loads(body_raw)
                except Exception as e:
                    messagebox.showerror("BODY JSON некорректен", str(e))
                    return

        self.status.config(text="Выполняю запрос... (см. Logs)")
        self.pretty_text.delete("1.0", tk.END)
        self.raw_text.delete("1.0", tk.END)

        def worker():
            try:
                resp, url = self.client.call(
                    m.http_method,
                    path_template,
                    path_params=path_params,
                    query_params=query_params,
                    body=body if body else None,
                )
                self.after(0, lambda r=resp, u=url: self._show_response(r, u))
            except Exception as e:
                self.after(0, lambda err=e: self._show_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _show_response(self, resp, url: str):
        self.status.config(text=f"{resp.status_code}  URL: {url}")

        text = resp.text or ""
        try:
            parsed = resp.json()
        except Exception:
            parsed = None

        headers = json.dumps(dict(resp.headers), ensure_ascii=False, indent=2)
        header_block = "=== RESPONSE HEADERS ===\n" + headers + "\n\n"

        if self.pretty_var.get() and parsed is not None:
            pretty_out = json.dumps(parsed, ensure_ascii=False, indent=2)
        else:
            pretty_out = text

        self.pretty_text.insert("1.0", header_block + pretty_out)
        self.raw_text.insert("1.0", header_block + text)
        self.resp_tabs.select(0)

    def _show_error(self, e: Exception):
        self.status.config(text="Ошибка запроса (см. Logs)")
        messagebox.showerror("Ошибка", str(e))
