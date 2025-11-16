from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RefactorSingleRequest(_message.Message):
    __slots__ = ("directory_path", "target_qualified_name", "old_qualified_name", "new_qualified_name")
    DIRECTORY_PATH_FIELD_NUMBER: _ClassVar[int]
    TARGET_QUALIFIED_NAME_FIELD_NUMBER: _ClassVar[int]
    OLD_QUALIFIED_NAME_FIELD_NUMBER: _ClassVar[int]
    NEW_QUALIFIED_NAME_FIELD_NUMBER: _ClassVar[int]
    directory_path: str
    target_qualified_name: str
    old_qualified_name: str
    new_qualified_name: str
    def __init__(self, directory_path: _Optional[str] = ..., target_qualified_name: _Optional[str] = ..., old_qualified_name: _Optional[str] = ..., new_qualified_name: _Optional[str] = ...) -> None: ...

class RefactorBatchTargetRequest(_message.Message):
    __slots__ = ("directory_path", "target_qualified_name", "replacement_map")
    DIRECTORY_PATH_FIELD_NUMBER: _ClassVar[int]
    TARGET_QUALIFIED_NAME_FIELD_NUMBER: _ClassVar[int]
    REPLACEMENT_MAP_FIELD_NUMBER: _ClassVar[int]
    directory_path: str
    target_qualified_name: str
    replacement_map: ReplacementMap
    def __init__(self, directory_path: _Optional[str] = ..., target_qualified_name: _Optional[str] = ..., replacement_map: _Optional[_Union[ReplacementMap, _Mapping]] = ...) -> None: ...

class ReplacementMap(_message.Message):
    __slots__ = ("replacements",)
    class ReplacementsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    REPLACEMENTS_FIELD_NUMBER: _ClassVar[int]
    replacements: _containers.ScalarMap[str, str]
    def __init__(self, replacements: _Optional[_Mapping[str, str]] = ...) -> None: ...

class RefactorAllRequest(_message.Message):
    __slots__ = ("directory_path", "replacements_per_target")
    class ReplacementsPerTargetEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: ReplacementMap
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[ReplacementMap, _Mapping]] = ...) -> None: ...
    DIRECTORY_PATH_FIELD_NUMBER: _ClassVar[int]
    REPLACEMENTS_PER_TARGET_FIELD_NUMBER: _ClassVar[int]
    directory_path: str
    replacements_per_target: _containers.MessageMap[str, ReplacementMap]
    def __init__(self, directory_path: _Optional[str] = ..., replacements_per_target: _Optional[_Mapping[str, ReplacementMap]] = ...) -> None: ...

class RefactorSingleResult(_message.Message):
    __slots__ = ("status", "modified_source", "error_message")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MODIFIED_SOURCE_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    status: int
    modified_source: str
    error_message: str
    def __init__(self, status: _Optional[int] = ..., modified_source: _Optional[str] = ..., error_message: _Optional[str] = ...) -> None: ...

class RefactorAllResult(_message.Message):
    __slots__ = ("target_qualified_name", "result")
    TARGET_QUALIFIED_NAME_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    target_qualified_name: str
    result: RefactorSingleResult
    def __init__(self, target_qualified_name: _Optional[str] = ..., result: _Optional[_Union[RefactorSingleResult, _Mapping]] = ...) -> None: ...
