from sqlalchemy import CheckConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column
from docweave.db.base import Base


class DeletionReceipt(Base):
    __tablename__ = 'deletion_receipts'
    __table_args__ = (CheckConstraint("hash ~ '^[0-9a-f]{64}$'", name='hash_format'),)
    hash: Mapped[str] = mapped_column(Text, primary_key=True)
