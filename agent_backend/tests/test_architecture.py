from pathlib import Path


def test_core_has_no_fastapi_imports() -> None:
    root = Path(__file__).parents[1] / "src" / "vinc_agent"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "fastapi" not in source.lower()
    assert "openai" not in source.lower()
