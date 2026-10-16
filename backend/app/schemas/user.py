from pydantic import BaseModel, ConfigDict

from app.schemas.reference import DepartmentOut


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: str
    department: DepartmentOut | None
