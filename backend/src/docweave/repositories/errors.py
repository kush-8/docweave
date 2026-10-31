"""Application SQLSTATEs are translated without choosing an HTTP response."""
SQL_ERRORS = {"P0002": "not_found", "42501": "forbidden", "DW001": "last_owner",
    "DW002": "already_member", "DW003": "revision_conflict", "DW004": "ingestion_active", "22023": "invalid_request"}

BUDGET_ERRORS = {"P0002": "not_found", "22023": "invalid_request", "DW010": "allowance_required", "DW011": "workspace_limit",
    "DW012": "application_capacity_unavailable", "DW013": "profile_unavailable", "DW014": "operation_conflict", "DW015": "settlement_conflict"}
