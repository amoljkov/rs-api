import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from rustore.config import get_settings
from rustore.token_manager import RuStoreTokenManager
from rustore.api_client import RuStoreApiClient
from rustore.methods import load_all, list_methods, MethodDef


def parse_typed(raw: str, type_name: str):
    if raw is None or raw == "":
        return None
    t = (type_name or "str").strip()
    if t == "int":
        return int(raw)
    if t == "float":
        return float(raw)
    if t == "bool":
        return raw.strip().lower() in ("1", "true", "yes", "y", "on")
    if t.startswith("list[") and t.endswith("]"):
        inner = t[5:-1].strip()
        items = [x.strip() for x in raw.split(",") if x.strip()]
        if inner == "int":
            return [int(x) for x in items]
        return items
    return raw


# ---------------- Clipboard hotkeys that work on RU/EN layouts ----------------
# Use keycodes (Windows):
#   A=65, C=67, V=86, X=88
def _is_ctrl(event) -> bool:
    # Control mask is 0x0004 on Windows Tk
    return (event.state & 0x0004) != 0


def bind_clipboard_shortcuts(widget: tk.Widget):
    """
    Guarantees Ctrl+A/C/V/X regardless of keyboard layout (RU/EN),
    and prevents double paste by returning exactly "break".
    Copy will copy ONLY selected text for Text/Entry widgets.
    """
    def on_key(event):
        if not _is_ctrl(event):
            return None

        if event.keycode == 65:  # Ctrl+A
            widget.event_generate("<<SelectAll>>")
            return "break"
        if event.keycode == 67:  # Ctrl+C
            widget.event_generate("<<Copy>>")
            return "break"
        if event.keycode == 88:  # Ctrl+X
            widget.event_generate("<<Cut>>")
            return "break"
        if event.keycode == 86:  # Ctrl+V
            widget.event_generate("<<Paste>>")
            return "break"

        return None

    widget.bind("<KeyPress>", on_key, add=True)

    widget.bind("<Control-Insert>", lambda e: (widget.event_generate("<<Copy>>"), "break")[1], add=True)
    widget.bind("<Shift-Insert>",   lambda e: (widget.event_generate("<<Paste>>"), "break")[1], add=True)
    widget.bind("<Shift-Delete>",   lambda e: (widget.event_generate("<<Cut>>"), "break")[1], add=True)


def add_context_menu(widget: tk.Widget):
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))   # selected only
    menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Select All", command=lambda: widget.event_generate("<<SelectAll>>"))

    def popup(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    widget.bind("<Button-3>", popup)
    widget.bind("<Shift-F10>", popup)


# ---------------- Tooltip (hints) ----------------
class Tooltip:
    """
    Lightweight tooltip for ttk/tk widgets.
    Shows on hover after a small delay.
    """
    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 450):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id = None
        self._tip = None

        widget.bind("<Enter>", self._schedule, add=True)
        widget.bind("<Leave>", self._hide, add=True)
        widget.bind("<ButtonPress>", self._hide, add=True)

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        if self._tip or not self.text:
            return

        # place tooltip near the widget
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8

        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")

        lbl = tk.Label(
            self._tip,
            text=self.text,
            justify="left",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=6,
            background="#ffffe0"
        )
        lbl.pack()

    def _hide(self, _event=None):
        self._cancel()
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


# ---------------- UI helpers: scrolled widgets ----------------
def make_scrolled_text(parent, *, wrap_mode: str = "word"):
    """
    Returns (frame, text_widget). Frame contains vertical+horizontal scrollbars.
    wrap_mode: "word" to wrap to window (no horizontal overflow), "none" to allow horizontal scroll.
    """
    frame = ttk.Frame(parent)
    text = tk.Text(frame, wrap=wrap_mode)

    ybar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=ybar.set)

    if wrap_mode == "none":
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(xscrollcommand=xbar.set)
        xbar.pack(side="bottom", fill="x")

    ybar.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)

    bind_clipboard_shortcuts(text)
    add_context_menu(text)
    return frame, text


def make_scrolled_treeview(parent):
    """
    Returns (frame, tree). Frame contains vertical+horizontal scrollbars.
    Used to display groups (non-clickable) and methods (clickable children).
    """
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, show="tree")
    ybar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    xbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)

    tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)

    ybar.pack(side="right", fill="y")
    xbar.pack(side="bottom", fill="x")
    tree.pack(side="left", fill="both", expand=True)
    return frame, tree


class ScrollFrame(ttk.Frame):
    """
    Scrollable area for parameter forms.
    Mousewheel is bound ONLY when cursor is over this frame,
    so it won't scroll other areas (response/logs).
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def _bind_wheel(self, _event=None):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_wheel(self, _event=None):
        self.canvas.unbind_all("<MouseWheel>")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RuStore Public API Client (Desktop)")
        self.geometry("1300x860")

        self.settings = get_settings()

        cfg = load_all("methods.yaml")
        self.methods: list[MethodDef] = list_methods(cfg)

        # map Treeview item -> MethodDef (only for method items, not group headers)
        self.method_by_iid: dict[str, MethodDef] = {}

        self.env_var = tk.StringVar(value="prod")
        self.pretty_var = tk.BooleanVar(value=True)

        self.path_entries = {}
        self.query_entries = {}

        self._build_ui()

        # after UI exists, init services with logger
        self.tm = RuStoreTokenManager(self.settings, logger=self.log)
        self.client = RuStoreApiClient(self.settings, self.tm, logger=self.log)

        self._populate_methods_tree()
        self._on_method_change()

        # set a sane initial split so the "Вызвать метод" button is always visible
        self.after(0, self._set_initial_sash)

    # -------- logging --------
    def log(self, msg: str):
        self.log_view.insert(tk.END, msg + "\n")
        self.log_view.see(tk.END)

    def _copy_text_widget_all(self, w: tk.Text):
        txt = w.get("1.0", tk.END).rstrip("\n")
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.status.config(text="Скопировано целиком в буфер обмена")

    # -------- initial layout --------
    def _set_initial_sash(self):
        """
        Ensure the top pane is tall enough so the call button is visible at start.
        We compute a minimum based on requested heights + extra padding.
        """
        try:
            # make sure geometry is calculated
            self.update_idletasks()

            total_h = self.right_split.winfo_height()
            if total_h <= 1:
                total_h = self.winfo_height()

            # ensure upper area is at least this many pixels
            upper_min = 430  # robust default for your current UI
            # but never more than total - 200 (keep some room for response)
            upper_target = min(max(int(total_h * 0.62), upper_min), max(total_h - 220, upper_min))

            self.right_split.sashpos(0, upper_target)
        except Exception:
            pass

    # -------- UI --------
    def _build_ui(self):
        root = ttk.PanedWindow(self, orient="horizontal")
        root.pack(fill="both", expand=True)

        left = ttk.Frame(root, padding=10)
        right = ttk.Frame(root, padding=10)
        root.add(left, weight=1)
        root.add(right, weight=5)

        # Left: env + methods tree (groups + methods)
        ttk.Label(left, text="Окружение").pack(anchor="w")
        env_box = ttk.Combobox(left, textvariable=self.env_var, values=["prod", "sandbox"], state="readonly")
        env_box.pack(fill="x", pady=(0, 10))
        env_box.bind("<<ComboboxSelected>>", lambda e: self._on_method_change())

        ttk.Label(left, text="Методы").pack(anchor="w")
        tree_frame, self.methods_tree = make_scrolled_treeview(left)
        tree_frame.pack(fill="both", expand=True)
        self.methods_tree.bind("<<TreeviewSelect>>", lambda e: self._on_tree_select())

        ttk.Button(left, text="Обновить токен (force refresh)", command=self._force_refresh_token).pack(fill="x", pady=8)

        # Right: method info (summary) — path is shown here (no endpoint box duplication)
        top = ttk.Frame(right)
        top.pack(fill="x")

        self.method_info = ttk.Label(top, text="", justify="left")
        self.method_info.pack(anchor="w")

        # Split right side into two vertical parts: upper (params) and lower (response/logs)
        self.right_split = tk.PanedWindow(right, orient="vertical", sashrelief="raised")
        self.right_split.pack(fill="both", expand=True)

        upper = ttk.Frame(self.right_split, padding=0)
        lower = ttk.Frame(self.right_split, padding=0)

        # minsize works in tk.PanedWindow (keep button visible)
        self.right_split.add(upper, stretch="always", minsize=460)
        self.right_split.add(lower, stretch="always", minsize=220)

        # Forms: path/query
        forms = ttk.PanedWindow(upper, orient="horizontal")
        forms.pack(fill="both", expand=True, pady=(10, 6))

        self.path_frame = ScrollFrame(forms)
        self.query_frame = ScrollFrame(forms)
        forms.add(self.path_frame, weight=1)
        forms.add(self.query_frame, weight=1)

        # BODY
        body_box = ttk.LabelFrame(upper, text="BODY (JSON)")
        body_box.pack(fill="x", pady=(0, 8))

        body_frame, self.body_text = make_scrolled_text(body_box, wrap_mode="word")
        body_frame.pack(fill="x", expand=False)
        self.body_text.configure(height=6)
        self.body_text.insert("1.0", "{}")

        # Call row
        call_row = ttk.Frame(upper)
        call_row.pack(fill="x", pady=(0, 10))

        ttk.Button(call_row, text="Вызвать метод", command=self._call_clicked).pack(side="left")
        ttk.Checkbutton(call_row, text="Pretty JSON", variable=self.pretty_var).pack(side="left", padx=12)

        # Lower: response + logs
        resp = ttk.LabelFrame(lower, text="Ответ / Логи")
        resp.pack(fill="both", expand=True, pady=(6, 0))

        # Toolbar for response (copy buttons here)
        resp_toolbar = ttk.Frame(resp)
        resp_toolbar.pack(fill="x", pady=(4, 2))
        ttk.Button(resp_toolbar, text="Copy Pretty (all)", command=lambda: self._copy_text_widget_all(self.pretty_view)).pack(side="right", padx=6)
        ttk.Button(resp_toolbar, text="Copy Raw (all)", command=lambda: self._copy_text_widget_all(self.raw_view)).pack(side="right")

        self.resp_tabs = ttk.Notebook(resp)
        self.resp_tabs.pack(fill="both", expand=True)

        pretty_frame, self.pretty_view = make_scrolled_text(self.resp_tabs, wrap_mode="word")
        raw_frame, self.raw_view = make_scrolled_text(self.resp_tabs, wrap_mode="none")
        logs_frame, self.log_view = make_scrolled_text(self.resp_tabs, wrap_mode="none")

        self.resp_tabs.add(pretty_frame, text="Pretty (wrap)")
        self.resp_tabs.add(raw_frame, text="Raw (scroll)")
        self.resp_tabs.add(logs_frame, text="Logs (scroll)")

        log_btn_row = ttk.Frame(resp)
        log_btn_row.pack(fill="x", pady=4)
        ttk.Button(log_btn_row, text="Clear logs", command=lambda: self.log_view.delete("1.0", tk.END)).pack(side="left")
        ttk.Button(log_btn_row, text="Copy logs (all)", command=lambda: self._copy_text_widget_all(self.log_view)).pack(side="left", padx=6)

        self.status = ttk.Label(right, text="", relief="sunken", anchor="w")
        self.status.pack(fill="x", side="bottom")

    # -------- methods tree --------
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

        # select first method
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
        # ignore group headers
        if iid not in self.method_by_iid:
            self.methods_tree.selection_remove(iid)
            return
        self._on_method_change()

    # -------- selection helpers --------
    def _selected_method(self) -> MethodDef | None:
        sel = self.methods_tree.selection()
        if not sel:
            return None
        return self.method_by_iid.get(sel[0])

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

        ttk.Label(parent_inner, text=title, font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 8), columnspan=2
        )

        r = 1
        for name, meta in (schema or {}).items():
            t = meta.get("type", "str")
            req = meta.get("required", False)
            hint = (meta.get("hint") or "").strip()

            label = f"{name} ({t})" + (" *" if req else "")
            ttk.Label(parent_inner, text=label).grid(row=r, column=0, sticky="w", padx=(0, 8), pady=4)

            e = ttk.Entry(parent_inner)
            e.grid(row=r, column=1, sticky="ew", pady=4)
            parent_inner.grid_columnconfigure(1, weight=1)

            bind_clipboard_shortcuts(e)
            add_context_menu(e)

            if hint:
                Tooltip(e, hint)

            store[name] = (e, meta)
            r += 1

        ttk.Label(parent_inner, text="* обязательные").grid(row=r, column=0, sticky="w", pady=(8, 0), columnspan=2)

    def _on_method_change(self):
        m = self._selected_method()
        if not m:
            return

        env = self.env_var.get()
        path = (m.paths or {}).get(env, "")
        full = f"{self.settings.base_url}{path}"

        # Show path clearly here (no separate endpoint box)
        self.method_info.config(
            text=f"{m.title}\n\nHTTP: {m.http_method}\nPath ({env}): {path}\nURL: {full}"
        )

        self._render_param_form(self.path_frame.inner, "PATH параметры", (m.params.get("path") or {}), self.path_entries)
        self._render_param_form(self.query_frame.inner, "QUERY параметры", (m.params.get("query") or {}), self.query_entries)

        self.pretty_view.delete("1.0", tk.END)
        self.raw_view.delete("1.0", tk.END)
        self.status.config(text="")

        # re-apply initial sash after method change (some methods have more fields)
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
                self.after(0, lambda: self._show_response(resp, url))
            except Exception as e:
                self.after(0, lambda: self._show_error(e))

        threading.Thread(target=worker, daemon=True).start()

    def _show_response(self, resp, url: str):
        self.status.config(text=f"{resp.status_code}  URL: {url}")

        text = resp.text or ""
        parsed = None
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


if __name__ == "__main__":
    App().mainloop()