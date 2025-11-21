from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.database.dropdown_db import DropdownOptions
from app.database.database import (
    engine,
    SkillDropdown,
    SpecializationDropdown,
    DomainDropdown,
    LocationDropdown,
    ManagerDropdown,
    CustomerDropdown,
)

router = APIRouter(prefix="/dropdown", tags=["dropdowns"])


async def get_session() -> AsyncSession:
    async with AsyncSession(engine) as session:
        yield session


@router.get("/skills")
async def get_skills(
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(SkillDropdown.skill_name)
    if q:
        stmt = stmt.where(SkillDropdown.skill_name.ilike(f"%{q}%"))
    stmt = stmt.order_by(SkillDropdown.skill_name).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())


@router.get("/specializations")
async def get_specializations(
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(SpecializationDropdown.specialization_name)
    if q:
        stmt = stmt.where(SpecializationDropdown.specialization_name.ilike(f"%{q}%"))
    stmt = stmt.order_by(SpecializationDropdown.specialization_name).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())


@router.get("/domains")
async def get_domains(
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(DomainDropdown.domain_name)
    if q:
        stmt = stmt.where(DomainDropdown.domain_name.ilike(f"%{q}%"))
    stmt = stmt.order_by(DomainDropdown.domain_name).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())


@router.get("/locations")
async def get_locations(
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(LocationDropdown.location_name)
    if q:
        stmt = stmt.where(LocationDropdown.location_name.ilike(f"%{q}%"))
    stmt = stmt.order_by(LocationDropdown.location_name).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())


@router.get("/managers")
async def get_managers(
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(ManagerDropdown.manager_name)
    if q:
        stmt = stmt.where(ManagerDropdown.manager_name.ilike(f"%{q}%"))
    stmt = stmt.order_by(ManagerDropdown.manager_name).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())


@router.get("/customers")
async def get_customers(
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(CustomerDropdown.customer_name)
    if q:
        stmt = stmt.where(CustomerDropdown.customer_name.ilike(f"%{q}%"))
    stmt = stmt.order_by(CustomerDropdown.customer_name).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())
