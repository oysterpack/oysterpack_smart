from sqlalchemy.orm import sessionmaker


class SqlAlchemySupport:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory
