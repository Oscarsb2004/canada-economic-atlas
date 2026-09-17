"""
Transform shells: pure operations that turn what was read into what is published.

No network, no clock. Where a transform can refuse its input, the caller may
pass its own error class, so a reader keeps its own error type and message.
"""
