from base import Base
from sqlalchemy.orm import Mapped, mapped_column

class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    #songs []
    #artists []
    #releaseDate

    def __repr__(self):
        return f"Album:\nId: {self.id}\n"
    