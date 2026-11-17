class ExternalServiceError(Exception):
    def __init__(self, service, message):
        super().__init__(message)
        self.service = service
        self.message = message


class RouteNotFound(Exception):
    pass


class LocationNotFound(Exception):
    def __init__(self, message, query=None, field=None):
        super().__init__(message)
        self.message = message
        self.query = query
        self.field = field


class LocationOutsideUSA(LocationNotFound):
    pass
