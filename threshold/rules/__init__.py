"""Rules: compiled once by a model, evaluated forever by code."""

from .compile import compile_rule, keyword_compile
from .evaluate import Clause, Decision, channels_for, evaluate, evaluate_all
from .geometry import point_in_polygon, polygon_area, zones_containing
from .model import CHANNELS, Rule

__all__ = [
    "Rule",
    "CHANNELS",
    "compile_rule",
    "keyword_compile",
    "evaluate",
    "evaluate_all",
    "channels_for",
    "Decision",
    "Clause",
    "point_in_polygon",
    "zones_containing",
    "polygon_area",
]
