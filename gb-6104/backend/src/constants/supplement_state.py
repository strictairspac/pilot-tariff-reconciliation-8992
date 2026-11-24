from enum import StrEnum


class SupplementState(StrEnum):
    ACTIVE = "active"
    FAILED = "failed"
    RETIRED = "retired"
