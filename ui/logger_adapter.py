class UiLogger:
    """
    Adapter compatible with logging.Logger-like API.
    Supports logger.info("x=%s", x) style calls.
    """

    def __init__(self, sink_func):
        self._sink = sink_func

    def _format(self, msg, *args):
        if args:
            try:
                msg = msg % args
            except Exception:
                msg = f"{msg} " + " ".join(map(str, args))
        return str(msg)

    def info(self, msg, *args):
        self._sink(self._format(msg, *args))

    def debug(self, msg, *args):
        self._sink(self._format(msg, *args))

    def warning(self, msg, *args):
        self._sink("WARN: " + self._format(msg, *args))

    def error(self, msg, *args):
        self._sink("ERROR: " + self._format(msg, *args))