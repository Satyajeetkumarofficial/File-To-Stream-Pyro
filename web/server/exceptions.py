class InvalidHash(Exception):
    message = "Invalid hash"

    def __init__(self, message: str = None):
        if message:
            self.message = message
        super().__init__(self.message)


class FIleNotFound(Exception):
    message = "File not found"

    def __init__(self, message: str = None):
        if message:
            self.message = message
        super().__init__(self.message)


# Correctly spelled alias
FileNotFound = FIleNotFound
