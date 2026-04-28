"""Execution plan CRUD with versioning."""
from uuid import UUID

from sqlalchemy.orm import Session

from core.db import models
from core.schemas import ExecutionPlan as PlanSchema


class PlanRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, plan: PlanSchema) -> models.ExecutionPlan:
        row = models.ExecutionPlan(
            id=plan.id,
            brief_id=plan.brief_id,
            version=plan.version,
            plan_json=plan.model_dump(mode="json"),
            status=plan.status,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def get(self, plan_id: UUID) -> models.ExecutionPlan | None:
        return self.db.get(models.ExecutionPlan, plan_id)

    def update_status(self, plan_id: UUID, status: str) -> None:
        row = self.db.get(models.ExecutionPlan, plan_id)
        if row is not None:
            row.status = status
            self.db.flush()

    def list_for_brief(self, brief_id: UUID) -> list[models.ExecutionPlan]:
        return list(
            self.db.query(models.ExecutionPlan)
            .filter(models.ExecutionPlan.brief_id == brief_id)
            .order_by(models.ExecutionPlan.version.desc())
        )
