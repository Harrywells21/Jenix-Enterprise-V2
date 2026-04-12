from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db import get_db, License, Machine
from auth import require_admin, User
from license import validate_license, generate_license

router = APIRouter(prefix="/license", tags=["license"])

class LicenseActivate(BaseModel):
    key: str

class LicenseGenerate(BaseModel):
    company_name: str
    max_nodes:    int  = -1

@router.get("")
def get_license(db: Session = Depends(get_db),
                _:  User    = Depends(require_admin)):
    lic = db.query(License).first()
    if not lic:
        return {"activated": False,
                "message": "No license activated"}
    return {
        "activated":    True,
        "company_name": lic.company_name,
        "max_nodes":    lic.max_nodes,
        "is_perpetual": lic.is_perpetual,
        "activated_at": lic.activated_at.isoformat(),
        "key_preview":  lic.key[:20] + "...",
    }

@router.post("/activate")
def activate_license(body: LicenseActivate,
                     db:   Session = Depends(get_db),
                     _:    User    = Depends(require_admin)):
    result = validate_license(body.key)
    if not result["valid"]:
        raise HTTPException(status_code=400,
                            detail=f"Invalid license: {result['error']}")
    # Check node limit
    node_count = db.query(Machine).count()
    if result["max_nodes"] != -1 and node_count > result["max_nodes"]:
        raise HTTPException(status_code=400,
                            detail=f"License allows {result['max_nodes']} nodes, "
                                   f"you have {node_count}")
    # Remove old license
    db.query(License).delete()
    lic = License(
        key          = body.key,
        company_name = result["company"],
        max_nodes    = result["max_nodes"],
        is_perpetual = result["perpetual"],
    )
    db.add(lic); db.commit()
    return {"ok": True, "company": result["company"],
            "max_nodes": result["max_nodes"]}

@router.post("/generate")
def gen_license(body: LicenseGenerate,
                _:    User = Depends(require_admin)):
    key = generate_license(body.company_name, body.max_nodes)
    return {"key": key, "company": body.company_name,
            "max_nodes": body.max_nodes}

@router.delete("")
def deactivate(db: Session = Depends(get_db),
               _:  User    = Depends(require_admin)):
    db.query(License).delete()
    db.commit()
    return {"ok": True}
