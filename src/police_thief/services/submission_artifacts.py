"""Building and validating the mandatory submission JSON bundle."""

from __future__ import annotations

from police_thief.services.submission_bundle import finalize_submission_bundle
from police_thief.services.submission_identity import (
    derive_game_uid,
    public_participant,
    save_submission_validation_report,
    series_consensus_hash,
    series_consensus_payload,
)
from police_thief.services.submission_schema import (
    SCHEMA_VERSION,
    SubmissionBundleError,
    SubmissionValidationError,
    canonical_bytes,
    canonical_hash,
    submission_filenames,
)
from police_thief.services.submission_validate import validate_submission_directory

__all__ = [
    "SCHEMA_VERSION",
    "SubmissionBundleError",
    "SubmissionValidationError",
    "canonical_bytes",
    "canonical_hash",
    "derive_game_uid",
    "finalize_submission_bundle",
    "public_participant",
    "save_submission_validation_report",
    "series_consensus_hash",
    "series_consensus_payload",
    "submission_filenames",
    "validate_submission_directory",
]
