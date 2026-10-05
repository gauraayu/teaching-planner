import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core.errors import NotFound
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import ImportSession, User
from app.schemas import requests as rq
from app.services import import_service as svc
from app.services import serializers as ser
from app.services.mapping_service import field_catalog

router = APIRouter(prefix="/imports", tags=["imports"])
IMPORTER = require(Permission.PLANS_IMPORT)


def _view(s: ImportSession) -> dict:
    return ser.import_session(s)


@router.get("/fields", dependencies=[Depends(IMPORTER)])
def fields():
    """Canonical portal fields the mapping UI offers."""
    return {"items": field_catalog()}


@router.get("", dependencies=[Depends(IMPORTER)])
def list_sessions(status: str | None = None, teaching_plan_id: uuid.UUID | None = None, db: Session = Depends(get_db)):
    stmt = select(ImportSession).order_by(ImportSession.updated_at.desc()).limit(100)
    if status:
        stmt = stmt.where(ImportSession.status.in_(status.split(",")))
    if teaching_plan_id:
        stmt = stmt.where(ImportSession.teaching_plan_id == teaching_plan_id)
    items = [ser.import_session(s, include_draft=False) for s in db.scalars(stmt)]
    return {"items": items, "total": len(items)}


@router.post("/session", status_code=201)
def create_session(body: rq.ImportSessionCreate, db: Session = Depends(get_db), user: User = Depends(IMPORTER)):
    return _view(svc.create_session(db, user, body.teaching_plan_id, resume=body.resume))


@router.get("/{session_id}", dependencies=[Depends(IMPORTER)])
def get_session(session_id: uuid.UUID, db: Session = Depends(get_db)):
    return _view(svc.get_session(db, session_id))


@router.delete("/{session_id}", status_code=204)
def discard_session(session_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(IMPORTER)):
    svc.discard(db, svc.get_session(db, session_id), user)


@router.put("/{session_id}/mode", dependencies=[Depends(IMPORTER)])
def set_mode(session_id: uuid.UUID, body: rq.ImportModeIn, db: Session = Depends(get_db)):
    return _view(svc.set_mode(db, svc.get_session(db, session_id), body.import_mode))


@router.post("/{session_id}/full-table", dependencies=[Depends(IMPORTER)])
def full_table(session_id: uuid.UUID, body: rq.FullTablePaste, db: Session = Depends(get_db)):
    s = svc.get_session(db, session_id)
    result = svc.load_full_table(db, s, body.raw_text, body.has_header)
    return {"result": result, "session": _view(s)}


@router.post("/{session_id}/file", dependencies=[Depends(IMPORTER)])
async def upload_file(session_id: uuid.UUID, file: UploadFile = File(...), sheet: str | None = Form(default=None),
                      db: Session = Depends(get_db)):
    s = svc.get_session(db, session_id)
    content = await file.read()
    result = svc.load_file(db, s, file.filename or "", content, sheet)
    return {"result": result, "session": _view(s)}


@router.put("/{session_id}/header", dependencies=[Depends(IMPORTER)])
def set_header(session_id: uuid.UUID, body: rq.HeaderToggle, db: Session = Depends(get_db)):
    return _view(svc.set_header(db, svc.get_session(db, session_id), body.has_header))


@router.put("/{session_id}/mapping", dependencies=[Depends(IMPORTER)])
def update_mapping(session_id: uuid.UUID, body: rq.MappingUpdateRequest, db: Session = Depends(get_db)):
    updates = {k: v.model_dump(exclude_unset=True) for k, v in body.columns.items()}
    return _view(svc.update_mapping(db, svc.get_session(db, session_id), updates))


@router.post("/{session_id}/mapping/confirm-suggestions", dependencies=[Depends(IMPORTER)])
def confirm_suggestions(session_id: uuid.UUID, db: Session = Depends(get_db)):
    return _view(svc.confirm_all_suggestions(db, svc.get_session(db, session_id)))


@router.post("/{session_id}/column", dependencies=[Depends(IMPORTER)])
def add_column(session_id: uuid.UUID, body: rq.ColumnPaste, db: Session = Depends(get_db)):
    s = svc.get_session(db, session_id)
    result = svc.add_column(db, s, field=body.field, raw_text=body.raw_text, order=body.order,
                            replace_key=body.replace_key, on_mismatch=body.on_mismatch)
    return {"result": result, "session": _view(s)}


@router.delete("/{session_id}/columns/{key}", dependencies=[Depends(IMPORTER)])
def clear_column(session_id: uuid.UUID, key: str, db: Session = Depends(get_db)):
    return _view(svc.clear_column(db, svc.get_session(db, session_id), key))


@router.post("/{session_id}/undo", dependencies=[Depends(IMPORTER)])
def undo(session_id: uuid.UUID, db: Session = Depends(get_db)):
    return _view(svc.undo_column_change(db, svc.get_session(db, session_id)))


@router.post("/{session_id}/validate", dependencies=[Depends(IMPORTER)])
def validate(session_id: uuid.UUID, db: Session = Depends(get_db)):
    s = svc.get_session(db, session_id)
    svc.validate(db, s)
    return {"session": _view(s), "preview": svc.preview(s)}


@router.get("/{session_id}/preview", dependencies=[Depends(IMPORTER)])
def preview(session_id: uuid.UUID, status: str | None = None, q: str | None = None, db: Session = Depends(get_db)):
    return svc.preview(svc.get_session(db, session_id), status=status, q=q)


@router.put("/{session_id}/rows/{index}", dependencies=[Depends(IMPORTER)])
def edit_row(session_id: uuid.UUID, index: int, body: rq.RowEdit, db: Session = Depends(get_db)):
    s = svc.edit_row(db, svc.get_session(db, session_id), index, body.values)
    svc.validate(db, s)
    return {"session": _view(s), "preview": svc.preview(s)}


@router.put("/{session_id}/rows/{index}/removed", dependencies=[Depends(IMPORTER)])
def remove_row(session_id: uuid.UUID, index: int, body: rq.RowRemoval, db: Session = Depends(get_db)):
    s = svc.set_row_removed(db, svc.get_session(db, session_id), index, body.removed)
    svc.validate(db, s)
    return {"session": _view(s), "preview": svc.preview(s)}


@router.post("/{session_id}/commit")
def commit(session_id: uuid.UUID, body: rq.ImportCommit, db: Session = Depends(get_db), user: User = Depends(IMPORTER)):
    s = svc.get_session(db, session_id)
    if not s:
        raise NotFound("Import session not found.")
    return svc.commit(db, s, user, publish=body.publish)
