"""ConvFill adapter for Hugging Face's realtime speech pipeline."""

__all__ = ["ConvFillRealtimeHandler", "register_convfill_backend"]


def __getattr__(name: str):
    """Keep package imports lazy so the server can apply startup shims first."""
    if name == "ConvFillRealtimeHandler":
        from .handler import ConvFillRealtimeHandler

        return ConvFillRealtimeHandler
    if name == "register_convfill_backend":
        from .backend import register_convfill_backend

        return register_convfill_backend
    raise AttributeError(name)
