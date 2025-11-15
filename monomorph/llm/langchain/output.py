from typing import Optional

from pydantic import BaseModel, Field


class RefactoringClass(BaseModel):
    """ The data regarding a new or refactored class """

    class_name: str = Field(description="The name of the class")
    package_name: str = Field(description="The package of the class")
    source_code: str = Field(description="The source code of the class")
    new_class: bool = Field(description="Whether the class is new or refactored")
    was_modified: bool = Field(description="Whether the class was modified if it was refactored")


class RPCSolution(BaseModel):
    """ The model's response when refactoring a local call to a remote call """

    explanation: str = Field(description="Explanation of the refactoring steps taken")
    new_classes: list[RefactoringClass] = Field(description="The new classes")
    rpc_method: str = Field(description="The qualified/full name of the new/refactored RPC method that should be called instead of the local method")
    additional_comments: str = Field(description="Additional comments regarding the refactoring")


class InvocationSolution(BaseModel):
    """ The model's response when refactoring a local invocation into an RPC """

    explanation: str = Field(description="Explanation of the refactoring steps taken")
    new_classes: list[RefactoringClass] = Field(description="The new classes")
    invoking_class: RefactoringClass = Field(description="The source code of the invoking method after the refactoring")
    additional_comments: str = Field(description="Additional comments regarding the refactoring")


class ProtoSolution(BaseModel):
    """ The model's structured response when generating a proto file """

    explanation: str = Field(description="Explanation of the refactoring steps taken")
    proto_code: str = Field(description="source code of the proto file")
    file_name: str = Field(description="The name of the proto file")
    service_name: str = Field(description="The name of the service")
    additional_comments: str = Field(description="Additional comments regarding the refactoring")


class GRPCSolution(BaseModel):
    """ The model's structured response when generating a gRPC client or server """

    explanation: str = Field(description="Explanation of the refactoring steps taken")
    new_class: RefactoringClass = Field(description="The new client or server class")
    additional_comments: str = Field(description="Additional comments regarding the refactoring")


class GRPCSolution2(BaseModel):
    """ The model's structured response when generating a gRPC client or server """

    class_name: str = Field(description="The name of the server or client class")
    package_name: str = Field(description="The package of the server or client class")
    source_code: str = Field(description="The source code of the server or client class")
    explanation: str = Field(description="Explanation of the refactoring steps taken")
    additional_comments: str = Field(description="Additional comments regarding the refactoring")


def from_refactoring_class_to_md(pydantic_output: RefactoringClass) -> str:
    md_output = ""
    md_output += f"### {pydantic_output.class_name}\n"
    md_output += f"Package: {pydantic_output.package_name}\n\n"
    md_output += f"This class is {'new' if pydantic_output.new_class else 'refactored'}\n\n"
    md_output += f"This class was {'modified' if pydantic_output.was_modified else 'not modified'}\n\n"
    md_output += f"```java\n{pydantic_output.source_code}\n```\n"
    return md_output


def from_solution_to_md(pydantic_output: BaseModel) -> str:
    if isinstance(pydantic_output, RPCSolution):
        return from_rpc_solution_to_md(pydantic_output)
    elif isinstance(pydantic_output, InvocationSolution):
        return from_invocation_solution_to_md(pydantic_output)
    elif isinstance(pydantic_output, ProtoSolution):
        return from_proto_solution_to_md(pydantic_output)
    elif isinstance(pydantic_output, GRPCSolution):
        return from_grpc_solution_to_md(pydantic_output)
    elif isinstance(pydantic_output, GRPCSolution2):
        return from_grpc_solution2_to_md(pydantic_output)
    else:
        raise TypeError("Invalid output type")


def from_grpc_solution_to_md(pydantic_output: GRPCSolution) -> str:
    sections = []
    # Explanation section
    md_output = ""
    md_output += f"## Explanation\n"
    md_output += f"{pydantic_output.explanation}\n"
    sections.append(md_output)
    # new_class section
    md_output = ""
    md_output += f"## New Classes\n"
    md_output += from_refactoring_class_to_md(pydantic_output.new_class)
    sections.append(md_output)
    # additional_comments section
    md_output = ""
    md_output += f"## Additional Comments\n"
    md_output += f"{pydantic_output.additional_comments}\n"
    sections.append(md_output)
    return "\n\n".join(sections)


def from_grpc_solution2_to_md(pydantic_output: GRPCSolution2) -> str:
    sections = []
    # Explanation section
    md_output = ""
    md_output += f"## Explanation\n"
    md_output += f"{pydantic_output.explanation}\n"
    sections.append(md_output)
    # new_class section
    md_output = ""
    md_output += f"## New Class\n"
    md_output += f"Class Name: {pydantic_output.class_name}\n"
    md_output += f"Package Name: {pydantic_output.package_name}\n"
    md_output += f"```java\n{pydantic_output.source_code}\n```\n"
    sections.append(md_output)
    # additional_comments section
    md_output = ""
    md_output += f"## Additional Comments\n"
    md_output += f"{pydantic_output.additional_comments}\n"
    sections.append(md_output)
    return "\n\n".join(sections)


def from_proto_solution_to_md(pydantic_output: ProtoSolution) -> str:
    sections = []
    # Explanation section
    md_output = ""
    md_output += f"## Explanation\n"
    md_output += f"{pydantic_output.explanation}\n"
    sections.append(md_output)
    # proto_code section
    md_output = ""
    md_output += f"## Proto File\n"
    md_output += f"File Name: {pydantic_output.file_name}\n"
    md_output += f"Service Name: {pydantic_output.service_name}\n"
    md_output += f"```proto\n{pydantic_output.proto_code}\n```\n"
    sections.append(md_output)
    # additional_comments section
    md_output = ""
    md_output += f"## Additional Comments\n"
    md_output += f"{pydantic_output.additional_comments}\n"
    sections.append(md_output)
    return "\n\n".join(sections)

def from_invocation_solution_to_md(pydantic_output: InvocationSolution) -> str:
    sections = []
    # Explanation section
    md_output = ""
    md_output += f"## Explanation\n"
    md_output += f"{pydantic_output.explanation}\n"
    sections.append(md_output)
    # rpc_method section
    md_output = ""
    md_output += f"## Invoking Method\n"
    md_output += from_refactoring_class_to_md(pydantic_output.invoking_class)
    sections.append(md_output)
    # additional_comments section
    md_output = ""
    md_output += f"## Additional Comments\n"
    md_output += f"{pydantic_output.additional_comments}\n"
    sections.append(md_output)
    # new_classes section
    md_output = ""
    md_output += f"## New Classes\n"
    for new_class in pydantic_output.new_classes:
        md_output += from_refactoring_class_to_md(new_class)
    sections.append(md_output)
    return "\n\n".join(sections)


def from_rpc_solution_to_md(pydantic_output: RPCSolution) -> str:
    sections = []
    # Explanation section
    md_output = ""
    md_output += f"## Explanation\n"
    md_output += f"{pydantic_output.explanation}\n"
    sections.append(md_output)
    # rpc_method section
    md_output = ""
    md_output += f"## RPC Method Name\n"
    md_output += f"{pydantic_output.rpc_method}\n"
    sections.append(md_output)
    # original_method section
    # md_output = ""
    # md_output += f"## Original Method\n"
    # if pydantic_output.original_method:
    #     md_output += from_refactoring_class_to_md(pydantic_output.original_method)
    # sections.append(md_output)
    # additional_comments section
    md_output = ""
    md_output += f"## Additional Comments\n"
    md_output += f"{pydantic_output.additional_comments}\n"
    sections.append(md_output)
    # new_classes section
    md_output = ""
    md_output += f"## New Classes\n"
    for new_class in pydantic_output.new_classes:
        md_output += from_refactoring_class_to_md(new_class)
    sections.append(md_output)

    return "\n\n".join(sections)