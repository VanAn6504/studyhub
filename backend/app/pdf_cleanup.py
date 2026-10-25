"""Commit file-removal intent with the database; retry filesystem failures."""
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.learning_models import PdfFileDeletion


def cleanup_pdf_files():
    base = get_settings().pdf_storage_path.resolve()
    with Session(get_engine()) as db:
        for row in db.scalars(select(PdfFileDeletion).with_for_update(skip_locked=True)).all():
            if not re.fullmatch(r'[0-9a-f]{32}\.pdf', row.storage_key):
                logging.getLogger(__name__).error('Invalid PDF cleanup key; retained for investigation.')
                continue
            path = (base / row.storage_key).resolve()
            if path.parent != base:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logging.getLogger(__name__).warning('PDF cleanup deferred; will retry on next cleanup or restart.')
                continue
            db.delete(row)
        db.commit()
