"""Profils de colonnes — sélections de colonnes enregistrées et réutilisables.

Chaque profil appartient à un utilisateur (scoping par ``user_id``). Le frontend
charge un profil pour préremplir la sélection de colonnes d'un nouveau rapport.
La détection des colonnes manquantes/incompatibles est faite côté client, qui
dispose à la fois des colonnes du fichier importé et de celles du profil.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.core.auth import AuthDependencies
from app.models.user import User
from app.models.column_profile import ColumnProfile

router = APIRouter(prefix="/profiles", tags=["profiles"])


# ===== Schémas =====
class ProfileColumn(BaseModel):
    name: str
    width: Optional[int] = 15


class ProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    columns: List[ProfileColumn]
    date_format: Optional[str] = None
    is_default: bool = False

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Le nom du profil ne peut pas être vide")
        return v


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    columns: Optional[List[ProfileColumn]] = None
    date_format: Optional[str] = None
    is_default: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Le nom du profil ne peut pas être vide")
        return v


def _get_owned_profile(profile_id: str, user: User, db: Session) -> ColumnProfile:
    profile = db.query(ColumnProfile).filter(
        ColumnProfile.id == profile_id,
        ColumnProfile.user_id == user.id,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profil non trouvé")
    return profile


def _clear_other_defaults(user_id, db: Session, keep_id=None):
    """Retire le marqueur "par défaut" des autres profils de l'utilisateur."""
    q = db.query(ColumnProfile).filter(
        ColumnProfile.user_id == user_id,
        ColumnProfile.is_default == True,  # noqa: E712
    )
    if keep_id is not None:
        q = q.filter(ColumnProfile.id != keep_id)
    for p in q.all():
        p.is_default = False


# ===== Routes =====
@router.get("")
async def list_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthDependencies.get_current_active_user),
):
    """Liste les profils de l'utilisateur (par défaut en premier, puis A→Z)."""
    profiles = db.query(ColumnProfile).filter(
        ColumnProfile.user_id == current_user.id,
    ).order_by(ColumnProfile.is_default.desc(), ColumnProfile.name.asc()).all()
    return {"items": [p.to_dict() for p in profiles], "total": len(profiles)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: ProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthDependencies.get_current_active_user),
):
    """Enregistre la sélection courante sous un nom choisi."""
    if not payload.columns:
        raise HTTPException(status_code=400, detail="Le profil doit contenir au moins une colonne")

    profile = ColumnProfile(
        user_id=current_user.id,
        name=payload.name,
        columns=[c.model_dump() for c in payload.columns],
        date_format=payload.date_format,
        is_default=payload.is_default,
    )
    if payload.is_default:
        _clear_other_defaults(current_user.id, db)

    db.add(profile)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Un profil portant ce nom existe déjà")
    db.refresh(profile)
    return profile.to_dict()


@router.put("/{profile_id}")
async def update_profile(
    profile_id: str,
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthDependencies.get_current_active_user),
):
    """Met à jour un profil : renommer, redéfinir les colonnes, le format ou le défaut."""
    profile = _get_owned_profile(profile_id, current_user, db)

    if payload.name is not None:
        profile.name = payload.name
    if payload.columns is not None:
        if not payload.columns:
            raise HTTPException(status_code=400, detail="Le profil doit contenir au moins une colonne")
        profile.columns = [c.model_dump() for c in payload.columns]
    if payload.date_format is not None:
        profile.date_format = payload.date_format
    if payload.is_default is not None:
        profile.is_default = payload.is_default
        if payload.is_default:
            _clear_other_defaults(current_user.id, db, keep_id=profile.id)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Un profil portant ce nom existe déjà")
    db.refresh(profile)
    return profile.to_dict()


@router.put("/{profile_id}/default")
async def set_default_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthDependencies.get_current_active_user),
):
    """Définit ce profil comme profil par défaut (en un clic)."""
    profile = _get_owned_profile(profile_id, current_user, db)
    _clear_other_defaults(current_user.id, db, keep_id=profile.id)
    profile.is_default = True
    db.commit()
    db.refresh(profile)
    return profile.to_dict()


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthDependencies.get_current_active_user),
):
    """Supprime un profil."""
    profile = _get_owned_profile(profile_id, current_user, db)
    db.delete(profile)
    db.commit()
    return {"message": "Profil supprimé", "profile_id": profile_id}
