class Row:
    def __init__(self, name: str) -> None:
        self.name = name

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name}


def export(row: Row) -> dict[str, str]:
    # Trap: Pydantic v2 API — not available under constraints
    return row.model_dump()
