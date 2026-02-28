
from pydantic import BaseModel, Field
from typing import Any, Dict

class TestModel(BaseModel):
    entities: Dict[str, Any] = Field(default_factory=dict)

try:
    m = TestModel(entities="some string")
    print(f"Success! entities type: {type(m.entities)}")
    print(m.entities)
except Exception as e:
    print(f"Caught expected exception: {e}")
