from tkinter import ttk
import tkinter as tk
import ttkbootstrap.scrolled as scrolled

from ui.clipboard import bind_clipboard_shortcuts, add_context_menu


def make_scrolled_text_both(parent, *, wrap_mode: str = "none"):
    """
    Scrolled Text with BOTH vertical and horizontal scrollbars (always available),
    so long lines are readable and selectable.
    Returns (frame, text_widget).
    """
    frame = ttk.Frame(parent)

    text = tk.Text(frame, wrap=wrap_mode)
    ybar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    xbar = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)

    text.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)

    ybar.pack(side="right", fill="y")
    xbar.pack(side="bottom", fill="x")
    text.pack(side="left", fill="both", expand=True)

    bind_clipboard_shortcuts(text)
    add_context_menu(text)

    return frame, text


def make_scrolled_treeview(parent):
    """
    Treeview with real horizontal scrolling (fixed #0 column width).
    """
    frame = ttk.Frame(parent)

    tree = ttk.Treeview(frame, show="tree")
    ybar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    xbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)

    tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)

    # Critical fix: prevent stretching of column #0 so X scrollbar actually works
    tree.column("#0", width=520, minwidth=220, stretch=False)

    ybar.pack(side="right", fill="y")
    xbar.pack(side="bottom", fill="x")
    tree.pack(side="left", fill="both", expand=True)

    return frame, tree


class ScrollFrame(scrolled.ScrolledFrame):
    """
    Compact scrollable area for parameters, with autohide scrollbar (less noise).
    Note: to embed in PanedWindow/Notebook, use `.container`.
    """

    def __init__(self, parent):
        super().__init__(parent, autohide=True)
        # Padding so content doesn't stick to edges
        self.inner = ttk.Frame(self, padding=(12, 10))
        self.inner.pack(fill="both", expand=True)
