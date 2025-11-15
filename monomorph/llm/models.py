from dataclasses import dataclass


@dataclass
class Class:
    name: str
    code: str
    full_name: str | None = None


@dataclass
class Method:
    name: str
    code: str
    class_: str
    full_name: str


@dataclass
class Language:
    name: str
    extension: str
    lowercase: str


LANGUAGE_MAP = {
    "java": Language("Java", "java", "java"),
    "python": Language("Python", "py", "python"),
    "csharp": Language("C#", "cs", "csharp"),
    "go": Language("Go", "go", "go"),
}
