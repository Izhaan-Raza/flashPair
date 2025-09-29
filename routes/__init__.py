# routes/__init__.py
from .auth import auth_bp
from .pair import pair_bp  
from .image import image_bp

__all__ = ['auth_bp', 'pair_bp', 'image_bp']
