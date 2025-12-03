from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.dropdown_db import DropdownOptions
from app.core.current_user import get_current_user_from_cookie
from app.database.database import (
    engine,
    SkillDropdown,
    SpecializationDropdown,
    DomainDropdown,
    LocationDropdown,
    ManagerDropdown,
    CustomerDropdown,
    CategoryDropdown,
    SubcategoryDropdown,
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
    current_user = Depends(get_current_user_from_cookie),
):
    """
    Получить список заказчиков.
    Возвращает только тех заказчиков, к которым у пользователя есть доступ.
    Если пользователь не авторизован или нет доступа - возвращает пустой список.
    """
    from app.database.admin_db import admin_repository
    
    # Если пользователь не авторизован - возвращаем пустой список
    if not current_user:
        return []
    
    # Получаем список ID заказчиков, к которым у пользователя есть доступ
    allowed_customer_ids = await admin_repository.get_user_customer_access(current_user.id)
    
    if not allowed_customer_ids:
        # Если нет доступа ни к одному заказчику - возвращаем пустой список
        return []
    
    stmt = select(CustomerDropdown.customer_name).where(
        CustomerDropdown.id.in_(allowed_customer_ids)
    )
    
    if q:
        stmt = stmt.where(CustomerDropdown.customer_name.ilike(f"%{q}%"))
    stmt = stmt.order_by(CustomerDropdown.customer_name).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())


@router.get("/categories")
async def get_categories(
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(CategoryDropdown.category_name)
    if q:
        stmt = stmt.where(CategoryDropdown.category_name.ilike(f"%{q}%"))
    stmt = stmt.order_by(CategoryDropdown.category_name).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())


@router.get("/subcategories")
async def get_subcategories(
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(SubcategoryDropdown.subcategory_name)
    if q:
        stmt = stmt.where(SubcategoryDropdown.subcategory_name.ilike(f"%{q}%"))
    stmt = stmt.order_by(SubcategoryDropdown.subcategory_name).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())
