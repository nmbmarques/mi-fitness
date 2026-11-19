"""Xiaomi account authentication subpackage.

Only ``XiaomiAuth`` is exposed publicly; internally it is split into separate modules per login method.
"""

from mi_fitness.auth.manager import XiaomiAuth

__all__ = ["XiaomiAuth"]
