from tkinter import ttk
import tkinter as tk
import ttkbootstrap.scrolled as scrolled

from ui.clipboard import bind_clipboard_shortcuts, add_context_menu


def make_scrolled_text(parent, *, wrap_mode: str = "word"):
    """
    ttkbootstrap ScrolledText is a Frame wrapper around a real tk.Text widget.
    We return (frame, text_widget) to keep .get/.insert logic stable.
    Scrollbars autohide => no visual noise when there's nothing to scroll.
    """
    frame = scrolled.ScrolledText(parent, autohide=True, wrap=wrap_mode)

    # ttkbootstrap keeps real Text widget inside `frame.text`
    text = getattr(frame, "text", None)
    if text is None:
        # fallback (shouldn't happen, but safe)
        text = frame

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
    tree.column("#0", width=520, minwidth=200, stretch=False)

    ybar.pack(side="right", fill="y")
    xbar.pack(side="bottom", fill="x")
    tree.pack(side="left", fill="both", expand=True)

    return frame, tree


class ScrollFrame(scrolled.ScrolledFrame):
    """
    ttkbootstrap ScrolledFrame has:
      - content frame (self)
      - outer container frame: self.container

    IMPORTANT:
      When adding to Notebook / PanedWindow, you must use `.container`
      (docs explicitly mention this). :contentReference[oaicite:1]{index=1}

    We also create `inner` with padding so labels/inputs don't stick to edges.
    """

    def __init__(self, parent):
        super().__init__(parent, autohide=True)
        self.inner = ttk.Frame(self, padding=(12, 10))
        self.inner.pack(fill="both", expand=True)