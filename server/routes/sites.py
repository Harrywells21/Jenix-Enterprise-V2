from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db import get_db, Site, Machine
from auth import get_current_user, require_admin, User

router = APIRouter(prefix="/sites", tags=["sites"])

class SiteCreate(BaseModel):
    name: str

@router.get("")
def list_sites(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    sites = db.query(Site).order_by(Site.name).all()
    result = []
    for s in sites:
        count = db.query(Machine).filter(Machine.site_id == s.id).count()
        result.append({"id": s.id, "name": s.name, "machine_count": count})
    return result

@router.post("")
def create_site(body: SiteCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    existing = db.query(Site).filter(Site.name == body.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="A site with this name already exists")
    site = Site(name=body.name)
    db.add(site); db.commit(); db.refresh(site)
    return {"id": site.id, "name": site.name}

@router.delete("/{site_id}")
def delete_site(site_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    db.query(Machine).filter(Machine.site_id == site_id).update({"site_id": None})
    db.delete(site); db.commit()
    return {"status": "deleted"}
