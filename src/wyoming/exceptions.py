"""
Custom exceptions used by the Wyoming package.
"""


class WyomingError(Exception):
    """Base exception for all Wyoming package errors."""


class DownloadError(WyomingError):
    """Raised when downloading sounding data fails."""


class NoDataError(WyomingError):
    """Raised when no sounding data exists for the requested launch."""


class ParsingError(WyomingError):
    """Raised when downloaded data cannot be parsed."""


class ProgressFileError(WyomingError):
    """Raised when reading or writing the progress file fails."""