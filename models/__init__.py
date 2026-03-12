# models/__init__.py
from .user import User

# If you add more models later (e.g., Room, Payment), add them here:
# from .room import Room
# from .payment import Payment

# This list makes it easy for Beanie to find everything
__all_models__ = [User]