from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from auth import require_admin, User
from backup import backup_now, list_backups, restore_backup
import os

router = APIRouter(prefix="/backup", tags=["backup"])

@router.post("/create")
def create_backup(_: User = Depends(require_admin)):
    path = backup_now()
    if not path:
        raise HTTPException(status_code=500,
                            detail="Backup failed — no database found")
    size = os.path.getsize(path) / 1024
    return {"ok": True, "path": path,
            "size_kb": round(size, 1)}

@router.get("/list")
def get_backups(_: User = Depends(require_admin)):
    return list_backups()

@router.post("/restore/{filename}")
def restore(filename: str, _: User = Depends(require_admin)):
    if not restore_backup(filename):
        raise HTTPException(status_code=404,
                            detail="Backup file not found")
    return {"ok": True, "restored": filename}
