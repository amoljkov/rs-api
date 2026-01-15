import tkinter as tk


# Windows keycodes:
# A=65, C=67, V=86, X=88
def _is_ctrl(event) -> bool:
    # Control mask is 0x0004 on Windows Tk
    return (event.state & 0x0004) != 0


def bind_clipboard_shortcuts(widget: tk.Widget):
    """
    Guarantees Ctrl+A/C/V/X regardless of keyboard layout (RU/EN),
    and prevents double paste by returning exactly "break".
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
    menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
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