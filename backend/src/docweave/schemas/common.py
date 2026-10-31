from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator


Nonblank = Annotated[str, Field(min_length=1, pattern=r"^[^\x00]*[^\s\x00][^\x00]*$")]
ContextText = Annotated[str, Field(pattern=r"^[^\x00]*$")]

class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        schema = handler(core_schema)
        # Omission is allowed for optional inputs; explicit null is rejected below.
        for field in schema.get("properties", {}).values():
            if "anyOf" in field:
                field["anyOf"] = [variant for variant in field["anyOf"] if variant.get("type") != "null"]
                field.pop("default", None)
        return schema

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null(cls, value):
        if isinstance(value, dict) and any(item is None for item in value.values()):
            raise ValueError("Omit optional fields instead of sending null.")
        return value
