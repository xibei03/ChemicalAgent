"""spec 里所有模型的共同基类。"""

from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    """冻结、不接受多余字段的模型。一经构造就不可变，所以序列字段一律用 tuple。"""

    model_config = ConfigDict(frozen=True, extra="forbid")
