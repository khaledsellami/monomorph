import logging

from langchain_core.messages import BaseMessage

from ..const import ApproachType
from ..planning.proxies import PlannedAPIClass


logger = logging.getLogger(__name__)


def get_referenced_class_mapping(class_name: str, api_classes: dict[str, PlannedAPIClass]) -> (
        dict)[str, dict[str, PlannedAPIClass]]:
    planned_api_class = api_classes[class_name]
    class_mapping = dict(idbased={}, dto={})
    for c in planned_api_class.referenced_classes:
        if c in api_classes:
            referenced_api_class = api_classes[c]
            approach = "idbased" if referenced_api_class.decision == ApproachType.ID_BASED else "dto"
            class_mapping[approach][c] = referenced_api_class
        else:
            logger.warning(f"Class {c} is referenced by {class_name} but not found in API classes.")
    return class_mapping


def format_messages(messages: list[BaseMessage]) -> str:
    """ Combines a list of langchain messages into a single string. """
    return "\n".join([f"{message.type}: {message.content}" for message in messages])