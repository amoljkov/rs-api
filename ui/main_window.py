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

from ui.widgets import make_scrolled_text, make_scrolled_treeview, ScrollFrame
from ui.clipboard import bind_clipboard_shortcuts, add_context_menu
from ui.tooltips import Tooltip
from ui.body_template import build_body_template, parse_typed
from ui.logger_adapter import UiLogger
from ui.layout import (
    RIGHT_SPLIT_UPPER_MINSIZE,
    RIGHT_SPLIT_LOWER_MINSIZE,
    RIGHT_SPLIT_SASH_START,
)


class MainWindow(tb.Window):
    def __init__(self):
        # Theme is intentionally hardcoded.
        # Available light themes you can try:
        # cosmo, flatly, journal, litera, lumen, minty, pulse, sandstone,
        # simplex, united, yeti, morph  :contentReference[oaicite:2]{index=2}
        super().__init__(themename="flatly")

        self.title("RuStore Public API Client")
        self.geometry("1360x900")

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

        self.after(0, self._set_initial_sash)

    # ---------------- logging ----------------
    def log(self, msg: str):
        self.log_view.insert(tk.END, str(msg) + "\n")
        self.log_view.see(tk.END)

    def _copy_text_widget_all(self, w: tk.Text):
        txt = w.get("1.0", tk.END).rstrip("\n")
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.status.config(text="Скопировано целиком в буфер обмена")

    # ---------------- layout ----------------
    def _set_initial_sash(self):
        try:
            self.update_idletasks()
            self.right_split.sashpos(0, RIGHT_SPLIT_SASH_START)
        except Exception:
            # fallback if tk throws in some cases
            try:
                self.right_split.sashpos(0, RIGHT_SPLIT_SASH_START)
            except Exception:
                pass

    # ---------------- UI build ----------------
    def _build_ui(self):
        root = ttk.PanedWindow(self, orient="horizontal")
        root.pack(fill="both", expand=True)

        left = ttk.Frame(root, padding=(14, 14))
        right = ttk.Frame(root, padding=(14, 14))
        root.add(left, weight=1)
        root.add(right, weight=5)

        # -------- Left (Sidebar) --------
        ttk.Label(left, text="Окружение", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        env_box = ttk.Combobox(left, textvariable=self.env_var, values=["prod", "sandbox"], state="readonly")
        env_box.pack(fill="x", pady=(6, 14))
        env_box.bind("<<ComboboxSelected>>", lambda e: self._on_method_change())

        ttk.Label(left, text="Методы", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tree_frame, self.methods_tree = make_scrolled_treeview(left)
        tree_frame.pack(fill="both", expand=True, pady=(6, 12))
        self.methods_tree.bind("<<TreeviewSelect>>", lambda e: self._on_tree_select())

        ttk.Button(left, text="Обновить токен", bootstyle="secondary", command=self._force_refresh_token).pack(fill="x")

        # -------- Right header --------
        header = ttk.Frame(right)
        header.pack(fill="x", pady=(0, 10))

        self.method_info = ttk.Label(
            header,
            text="",
            justify="left",
            font=("Segoe UI", 10),
        )
        self.method_info.pack(anchor="w")

        # -------- Right split --------
        self.right_split = tk.PanedWindow(right, orient="vertical", sashrelief="raised")
        self.right_split.pack(fill="both", expand=True)

        upper = ttk.Frame(self.right_split)
        lower = ttk.Frame(self.right_split)

        self.right_split.add(upper, minsize=RIGHT_SPLIT_UPPER_MINSIZE)
        self.right_split.add(lower, minsize=RIGHT_SPLIT_LOWER_MINSIZE)

        # -------- Forms --------
        forms = ttk.PanedWindow(upper, orient="horizontal")
        forms.pack(fill="both", expand=True, pady=(8, 10))

        self.path_frame = ScrollFrame(forms)
        self.query_frame = ScrollFrame(forms)

        # IMPORTANT: ttkbootstrap ScrolledFrame must be added via `.container` in PanedWindow :contentReference[oaicite:3]{index=3}
        forms.add(self.path_frame.container, weight=1)
        forms.add(self.query_frame.container, weight=1)

        # -------- BODY --------
        body_box = ttk.Labelframe(upper, text="BODY (JSON)", padding=(10, 8))
        body_box.pack(fill="x", pady=(0, 12))

        body_frame, self.body_text = make_scrolled_text(body_box, wrap_mode="word")
        body_frame.pack(fill="x")
        self.body_text.configure(height=7)

        def on_body_modified(_e=None):
            self.body_text.edit_modified(False)
            self._body_dirty = True

        self.body_text.bind("<<Modified>>", on_body_modified, add=True)
        self.body_text.edit_modified(False)

        # -------- Call row --------
        call_row = ttk.Frame(upper)
        call_row.pack(fill="x", pady=(0, 10))

        ttk.Button(call_row, text="Вызвать метод", bootstyle="primary", command=self._call_clicked).pack(side="left")
        ttk.Checkbutton(
            call_row,
            text="Pretty JSON",
            variable=self.pretty_var,
            bootstyle="round-toggle",
        ).pack(side="left", padx=14)

        # -------- Lower: Response + Logs --------
        resp = ttk.Labelframe(lower, text="Ответ / Логи", padding=(10, 8))
        resp.pack(fill="both", expand=True, pady=(6, 0))

        resp_toolbar = ttk.Frame(resp)
        resp_toolbar.pack(fill="x", pady=(4, 6))

        # We'll attach these buttons to response area (not params)
        ttk.Button(
            resp_toolbar,
            text="Copy Pretty",
            bootstyle="secondary-outline",
            command=lambda: self._copy_text_widget_all(self.pretty_view),
        ).pack(side="right", padx=6)

        ttk.Button(
            resp_toolbar,
            text="Copy Raw",
            bootstyle="secondary-outline",
            command=lambda: self._copy_text_widget_all(self.raw_view),
        ).pack(side="right")

        self.resp_tabs = ttk.Notebook(resp)
        self.resp_tabs.pack(fill="both", expand=True, pady=(2, 6))

        pretty_frame, self.pretty_view = make_scrolled_text(self.resp_tabs, wrap_mode="word")
        raw_frame, self.raw_view = make_scrolled_text(self.resp_tabs, wrap_mode="none")
        logs_frame, self.log_view = make_scrolled_text(self.resp_tabs, wrap_mode="none")

        self.resp_tabs.add(pretty_frame, text="Pretty")
        self.resp_tabs.add(raw_frame, text="Raw")
        self.resp_tabs.add(logs_frame, text="Logs")

        log_btn_row = ttk.Frame(resp)
        log_btn_row.pack(fill="x", pady=(0, 6))

        ttk.Button(
            log_btn_row,
            text="Clear logs",
            bootstyle="secondary-outline",
            command=lambda: self.log_view.delete("1.0", tk.END),
        ).pack(side="left")

        ttk.Button(
            log_btn_row,
            text="Copy logs",
            bootstyle="secondary-outline",
            command=lambda: self._copy_text_widget_all(self.log_view),
        ).pack(side="left", padx=8)

        self.status = ttk.Label(right, text="", anchor="w", foreground="#555")
        self.status.pack(fill="x", side="bottom", pady=(10, 0))

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

    def _clear_frame(self, frame: ttk.Frame):
        for w in frame.winfo_children():
            w.destroy()

    def _render_param_form(self, parent_inner: ttk.Frame, title: str, schema: dict, store: dict):
        self._clear_frame(parent_inner)
        store.clear()

        ttk.Label(parent_inner, text=title, font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 10), columnspan=2
        )

        r = 1
        for name, meta in (schema or {}).items():
            t = (meta.get("type") or "str")
            req = bool(meta.get("required", False))
            hint = (meta.get("hint") or "").strip()

            label = f"{name} ({t})" + (" *" if req else "")
            ttk.Label(parent_inner, text=label).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=6)

            e = ttk.Entry(parent_inner)
            e.grid(row=r, column=1, sticky="ew", pady=6)
            parent_inner.grid_columnconfigure(1, weight=1)

            bind_clipboard_shortcuts(e)
            add_context_menu(e)

            if hint:
                Tooltip(e, hint)

            store[name] = (e, meta)
            r += 1

        ttk.Label(parent_inner, text="* обязательные", foreground="#666").grid(
            row=r, column=0, sticky="w", pady=(10, 0), columnspan=2
        )

    def _on_method_change(self):
        m = self._selected_method()
        if not m:
            return

        env = self.env_var.get()
        path = (m.paths or {}).get(env, "")
        full = f"{self.settings.base_url}{path}"

        self.method_info.config(
            text=f"{m.title}\nHTTP: {m.http_method}    Path ({env}): {path}\nURL: {full}"
        )

        self._render_param_form(self.path_frame.inner, "PATH параметры", (m.params.get("path") or {}), self.path_entries)
        self._render_param_form(self.query_frame.inner, "QUERY параметры", (m.params.get("query") or {}), self.query_entries)

        sel = self.methods_tree.selection()
        current_iid = sel[0] if sel else None
        method_changed = (current_iid != self._current_method_iid)

        if method_changed:
            self._current_method_iid = current_iid
            self._body_dirty = False

        body_schema = (m.params.get("body") or {})
        if not self._body_dirty:
            template = build_body_template(body_schema)
            self.body_text.delete("1.0", tk.END)
            self.body_text.insert("1.0", json.dumps(template, ensure_ascii=False, indent=2))
            self.body_text.edit_modified(False)

        self.pretty_view.delete("1.0", tk.END)
        self.raw_view.delete("1.0", tk.END)
        self.status.config(text="")

        self.after(0, self._set_initial_sash)

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

        body_raw = self.body_text.get("1.0", tk.END).strip()
        try:
            body = json.loads(body_raw) if body_raw else {}
        except Exception as e:
            messagebox.showerror("BODY JSON некорректен", str(e))
            return

        self.status.config(text="Выполняю запрос... (см. Logs)")
        self.pretty_view.delete("1.0", tk.END)
        self.raw_view.delete("1.0", tk.END)

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

        header_block = "=== RESPONSE HEADERS ===\n" + json.dumps(dict(resp.headers), ensure_ascii=False, indent=2) + "\n\n"

        if self.pretty_var.get() and parsed is not None:
            pretty_out = json.dumps(parsed, ensure_ascii=False, indent=2)
        else:
            pretty_out = text

        self.pretty_view.insert("1.0", header_block + pretty_out)
        self.raw_view.insert("1.0", header_block + text)

    def _show_error(self, e: Exception):
        self.status.config(text="Ошибка запроса (см. Logs)")
        messagebox.showerror("Ошибка", str(e))
