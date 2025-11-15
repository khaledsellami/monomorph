import importlib.resources
import json
import logging

from .._metadata import PACKAGE_NAME


with importlib.resources.open_text(f'{PACKAGE_NAME}.resources', f'model_map.json') as f:
    MODEL_MAP = json.load(f)


def get_model(name: str, block_paid_api: bool = True) -> str:
    logger = logging.getLogger(PACKAGE_NAME)
    if name in MODEL_MAP["free"]:
        full_name = MODEL_MAP["free"].get(name)
    elif name in MODEL_MAP["paid"]:
        if block_paid_api:
            logger.error(f"Paid model {name} is blocked!")
            raise ValueError(f"Paid model {name} is blocked!")
        logger.warning(f"Using paid model {name}")
        full_name = MODEL_MAP["paid"].get(name)
    else:
        logger.error(f"Model {name} not found!")
        raise ValueError(f"Model {name} not found!")
    return full_name



