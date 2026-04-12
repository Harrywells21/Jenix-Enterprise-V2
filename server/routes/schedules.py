from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db import get_db, Schedule, Machine
from auth import get_current_user, require_operator, User
from scheduler import add_schedule, remove_schedule

router = APIRouter(prefix="/schedules", tags=["schedules"])

class ScheduleCreate(BaseModel):
    machine_id: int
    scan_type:  str = "security"
    frequency:  str = "daily"
    hour:       int = 2

class ScheduleOut(BaseModel):
    id:         int
    machine_id: int
    scan_type:  str
    frequency:  str
    hour:       int
    is_active:  bool
    class Config:
        from_attributes = True

@router.get("", response_model=list[ScheduleOut])
def list_schedules(db: Session = Depends(get_db),
                   _:  User    = Depends(get_current_user)):
    return db.query(Schedule).all()

@router.post("", response_model=ScheduleOut)
def create_schedule(body: ScheduleCreate,
                    db:   Session = Depends(get_db),
                    _:    User    = Depends(require_operator)):
    m = db.query(Machine).filter(Machine.id == body.machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    s = Schedule(machine_id=body.machine_id, scan_type=body.scan_type,
                 frequency=body.frequency, hour=body.hour)
    db.add(s); db.commit(); db.refresh(s)
    add_schedule(s)
    return s

@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: int,
                    db: Session = Depends(get_db),
                    _:  User    = Depends(require_operator)):
    s = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    remove_schedule(schedule_id)
    db.delete(s); db.commit()
    return {"ok": True}

@router.patch("/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int,
                    db: Session = Depends(get_db),
                    _:  User    = Depends(require_operator)):
    s = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    s.is_active = not s.is_active
    db.commit()
    if s.is_active:
        add_schedule(s)
    else:
        remove_schedule(schedule_id)
    return {"ok": True, "is_active": s.is_active}
