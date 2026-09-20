"""Exception hierarchy for the IDP pipeline. Caught centrally at the UI boundary."""


class IDPBaseError(Exception):
    """Base exception for all IDP pipeline errors."""


class DocumentProcessingError(IDPBaseError):
    """Raised when a document cannot be rendered or decoded."""


class ExtractionError(IDPBaseError):
    """Raised when the vision model call or schema validation fails."""


class ExtractionTimeoutError(ExtractionError):
    """Raised when extraction exceeds the processing timeout safeguard."""


class ReconciliationError(IDPBaseError):
    """Raised when the ledger reconciliation engine fails."""
