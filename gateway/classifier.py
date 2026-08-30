"""
Data classifier - classifies text as RED/YELLOW/GREEN
Based on pattern matching against configuration
"""

import logging
import re
from typing import Any, List, Tuple
from enum import Enum

from config import settings

logger = logging.getLogger(__name__)


class DataClass(str, Enum):
    """Data classification levels"""
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"


class Classification:
    """Result of data classification"""
    
    def __init__(self, level: DataClass, patterns: List[str]):
        self.level = level
        self.patterns = patterns  # Matched pattern descriptions
    
    def __repr__(self):
        return f"Classification(level={self.level}, patterns={self.patterns})"


class DataClassifier:
    """Classifies text data by pattern matching"""
    
    def __init__(self):
        # Load patterns from configuration
        self.red_patterns = self._compile_patterns(settings.red_patterns)
        self.yellow_patterns = self._compile_patterns(settings.yellow_patterns)
        
        logger.info(
            f"DataClassifier initialized: "
            f"red_patterns={len(self.red_patterns)}, "
            f"yellow_patterns={len(self.yellow_patterns)}"
        )
    
    def classify(self, text: str) -> Classification:
        """
        Classify text as RED, YELLOW, or GREEN
        
        Hierarchy: RED > YELLOW > GREEN
        (RED is highest sensitivity, GREEN is lowest)
        
        Args:
            text: Text to classify
            
        Returns:
            Classification object with level and matched patterns
        """
        # Check RED patterns first (highest priority)
        red_matches = self._find_matches(text, self.red_patterns)
        if red_matches:
            logger.debug(f"Text classified as RED: {red_matches}")
            return Classification(DataClass.RED, red_matches)
        
        # Check YELLOW patterns
        yellow_matches = self._find_matches(text, self.yellow_patterns)
        if yellow_matches:
            logger.debug(f"Text classified as YELLOW: {yellow_matches}")
            return Classification(DataClass.YELLOW, yellow_matches)
        
        # Default to GREEN
        logger.debug("Text classified as GREEN")
        return Classification(DataClass.GREEN, [])
    
    def _compile_patterns(self, pattern_list: List[Any]) -> List[Tuple[str, re.Pattern]]:
        """
        Compile pattern strings to regex objects
        
        Args:
            pattern_list: List of regex pattern strings
            
        Returns:
            List of (pattern_str, compiled_regex) tuples
        """
        compiled = []
        
        for configured_pattern in pattern_list:
            if isinstance(configured_pattern, dict):
                pattern_str = configured_pattern.get("pattern", "")
                pattern_name = configured_pattern.get("name", pattern_str)
            else:
                pattern_str = configured_pattern
                pattern_name = pattern_str

            try:
                # Compile with case-insensitive flag
                compiled_pattern = re.compile(pattern_str, re.IGNORECASE)
                compiled.append((pattern_name, compiled_pattern))
            except re.error as e:
                logger.error(f"Invalid regex pattern: {pattern_str}: {e}")
        
        return compiled
    
    def _find_matches(self, text: str, patterns: List[Tuple[str, re.Pattern]]) -> List[str]:
        """
        Find all matching patterns in text
        
        Args:
            text: Text to search
            patterns: List of (pattern_str, compiled_regex) tuples
            
        Returns:
            List of matched pattern descriptions
        """
        matches = []
        
        for pattern_name, regex in patterns:
            if regex.search(text):
                matches.append(pattern_name)
        
        return matches


# Global classifier instance
_classifier = DataClassifier()


def classify_data(text: str) -> Classification:
    """
    Classify data as RED/YELLOW/GREEN
    
    Args:
        text: Text to classify
        
    Returns:
        Classification object
    """
    return _classifier.classify(text)


def get_classifier() -> DataClassifier:
    """Get the global classifier instance"""
    return _classifier


def redact_red_data(text: str) -> str:
    """Redact values matched by the same RED rules used for classification."""
    redacted = text
    for pattern_name, regex in _classifier.red_patterns:
        redacted = regex.sub(f"[REDACTED:{pattern_name}]", redacted)
    return redacted


def redact_sensitive_value(value: Any) -> Any:
    """Recursively redact RED strings in JSON-compatible audit values."""
    if isinstance(value, str):
        return redact_red_data(value)
    if isinstance(value, dict):
        return {key: redact_sensitive_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive_value(item) for item in value]
    return value
