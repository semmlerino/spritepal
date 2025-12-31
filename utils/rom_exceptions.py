"""
ROM-specific exceptions for SpritePal
"""


class ROMError(Exception):
    """Base exception for ROM-related errors"""


class InvalidROMError(ROMError):
    """Raised when ROM file is invalid or corrupted"""


class ROMChecksumError(ROMError):
    """Raised when ROM checksum validation fails"""


class ROMHeaderError(ROMError):
    """Raised when ROM header is invalid or missing"""


class ROMSizeError(ROMError):
    """Raised when ROM size is invalid"""


class ROMVersionError(ROMError):
    """Raised when ROM version/region is unsupported"""


class ROMCompressionError(ROMError):
    """Raised when compression/decompression fails"""


class ROMInjectionError(ROMError):
    """Raised when sprite injection fails"""


class ROMExtractionError(ROMError):
    """Raised when sprite extraction fails"""


class ROMBackupError(ROMError):
    """Raised when backup creation fails"""


class ROMOffsetError(ROMError):
    """Raised when offset is out of bounds or invalid"""
