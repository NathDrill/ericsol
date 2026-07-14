from pydantic import BaseModel


class VendorOut(BaseModel):
    id: int
    name: str
    aliases: list[str] = []

    class Config:
        from_attributes = True


class VendorIn(BaseModel):
    name: str
    aliases: list[str] = []

