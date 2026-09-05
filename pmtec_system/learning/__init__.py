"""ASDA Adapt Learning Module - Online learning for PMTEC digital twin.
UCB1 intercept strategy + Q-learning dispersal paths + sensor deployment optimization.
No CUDA/GPU dependency - pure NumPy implementation for Windows + Intel Arc.
"""

from .learning_manager import LearningManager

__all__ = ["LearningManager"]
