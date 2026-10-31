"""Transport-independent failures; HTTP mapping belongs to the API."""
class DomainError(Exception):
    def __init__(self, code, *, headers=None):
        self.code = code
        self.headers = headers
        super().__init__(code)


class BudgetError(DomainError):
    pass
