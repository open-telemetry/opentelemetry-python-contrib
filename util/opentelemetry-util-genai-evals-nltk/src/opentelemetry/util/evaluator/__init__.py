"""Evaluator plug-ins for OpenTelemetry GenAI utilities (NLTK)."""

from .nltk import NLTKSentimentEvaluator, register, registration

__all__ = ["NLTKSentimentEvaluator", "register", "registration"]
