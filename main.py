import logging
import json
import os
import shutil
import time
from argparse import Namespace
from datetime import datetime
from typing import Optional

from langchain_community.cache import SQLiteCache
from langchain_core.globals import set_llm_cache
import colorlog

from monomorph import __version__, __analysis_version__, __importparser_version__
from monomorph.assembly.entrypoint import EntryPointGenerator
from monomorph.llm.tracking.checkpoints import CheckpointStorage
from monomorph.models import Decomposition
from monomorph.monomorph import MonoMorph
from monomorph.llm.langchain.prompts import (
    LangChainGrpcParsingPrompt,
    LangChainProtoParsingPrompt,
    LangChainIDgRPCProtoPrompt,
    LangChainIDgRPCServerPrompt,
    LangChainIDgRPCClientPrompt
)


def setup_logging(app: str, log_file_path: str = os.path.join(os.curdir, "refact_logs.log")):
    """Setup colored console and file logging."""
    root_logger = logging.getLogger()
    # Remove existing StreamHandlers to avoid duplicate logs (happens when some modules add their own handlers)
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            if isinstance(handler, logging.StreamHandler) and handler.stream.name == '<stderr>':
                root_logger.removeHandler(handler)

    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s [%(thread)d] %(name)s %(levelname)s %(filename)s:%(lineno)d - %(message)s'))
    logging.getLogger("monomorph").addHandler(handler)

    fileHandler = logging.FileHandler(log_file_path, mode='w')
    fileHandler.setFormatter(logging.Formatter(
        app + ' %(asctime)s [%(thread)d] %(name)s %(levelname)s %(filename)s:%(lineno)d - %(message)s'
    ))
    logging.getLogger("monomorph").addHandler(fileHandler)
    logging.getLogger("monomorph").setLevel(logging.DEBUG)

    return logging.getLogger("monomorph"), log_file_path


def get_git_hash():
    """Get current git commit hash."""
    try:
        import subprocess
        return subprocess.check_output(['git', 'rev-parse', 'HEAD']).strip().decode('utf-8')
    except Exception as e:
        logging.error(f"Error getting git hash: {e}")
        return None


def save_experiment_metadata(monomorph_run: MonoMorph, args: Namespace, start_time: int, cpu_start_time: int,
                             start_timestamp: str, timestamp_short: str, exp_data_path: Optional[str] = None):
    """Save experiment tracking metadata and profiling information."""
    logger = logging.getLogger("monomorph")
    logger.debug("Preparing profiling data")

    git_hash = get_git_hash()
    end_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    end_time = time.perf_counter_ns()
    cpu_end_time = time.process_time_ns()
    wall_time = end_time - start_time
    cpu_time = cpu_end_time - cpu_start_time

    args_dict = {
        "run_id": monomorph_run.run_id,
        "run_instance": monomorph_run.directory_name,
        "input_arguments": {
            "app": args.app,
            "app_source_code_path": args.app_source_code_path,
            "package": args.package,
            "java_version": args.java_version,
            "decomposition_file": args.decomposition_file,
            "refact_model_name": args.refact_model,
            "parser_model_name": args.parser_model,
            "decision_model_name": args.decision_model,
            "correction_model_name": args.correction_model,
            "include_tests": args.include_tests,
            "restrictive": args.restrictive,
            "llm_cache_path": args.llm_cache_path,
            "use_llm_cache": args.use_llm_cache,
            "llm_checkpoint_path": str(CheckpointStorage()._storage_path),
            "checkpoint_config": {
                "path": args.llm_checkpoints_path,
                "should_load": args.checkpoint_load,
                "should_save": args.checkpoint_save
            },
            "original_dockerfile_path": args.original_dockerfile_path
        },
        "other_arguments": {
            "defaultFreq": 20000,
            "freqStr": "LEASE_RENEWAL_FREQUENCY_MS",
            "default_lease_duration": EntryPointGenerator.DEFAULT_LEASE_DURATION,
            "lease_duration_env_var_name": EntryPointGenerator.LEASE_DURATION_ENV_VAR_NAME,
        },
        "monomorph_versions": {
            "monomorph_version": __version__,
            "analysis_version": __analysis_version__,
            "importparser_version": __importparser_version__,
            "LangChainProtoParsingPrompt_version": LangChainProtoParsingPrompt.VERSION,
            "LangChainGrpcParsingPrompt_version": LangChainGrpcParsingPrompt.VERSION,
            "LangChainIDgRPCProtoPrompt_version": LangChainIDgRPCProtoPrompt.VERSION,
            "LangChainIDgRPCServerPrompt_version": LangChainIDgRPCServerPrompt.VERSION,
            "LangChainIDgRPCClientPrompt_version": LangChainIDgRPCClientPrompt.VERSION,
            "git_hash": git_hash,
            "refact_approach": args.refact_approach,
            "with_validation": True
        },
        "profiling": {
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "wall_time": wall_time,
            "cpu_time": cpu_time,
            "start_time": start_time,
            "end_time": end_time,
            "cpu_start_time": cpu_start_time,
            "cpu_end_time": cpu_end_time,
            "timestamp_short": timestamp_short,
        }
    }

    filename = f"{args.app}-{timestamp_short}-{monomorph_run.run_id[:4]}-metadata.json"
    if exp_data_path is None:
        exp_data_path = monomorph_run.project.project_path
    os.makedirs(exp_data_path, exist_ok=True)
    logger.debug(f"Saving arguments to {os.path.join(exp_data_path, filename)}")
    with open(os.path.join(exp_data_path, filename), "w") as f:
        json.dump(args_dict, f, indent=4)


def run_monomorph(
        app: str,
        app_source_code_path: str,
        decomposition_file: str,
        package: str,
        java_version: str,
        build_tool: str,
        original_dockerfile_path: str,
        refact_approach: str = "Hybrid",
        refact_model: str = "gemini-2.5-pro",
        parser_model: str = "ministral-8b",
        decision_model: str = "gemini-2.5-pro",
        correction_model: str = "gemini-2.5-pro",
        fallback_model: str = "gemini-2.5-pro",
        analysis_data_path: str = os.path.join(os.curdir, "data", "analysis"),
        out_path: Optional[str] = None,
        refactored_code_path: Optional[str] = None,
        llm_response_path: Optional[str] = None,
        llm_checkpoints_path: Optional[str] = None,
        exp_data_path: Optional[str] = None,
        include_tests: bool = False,
        restrictive: bool = True,
        use_llm_cache: bool = True,
        reset_cache: bool = False,
        llm_cache_path: str = ".langchain.db",
        checkpoint_load: bool = True,
        checkpoint_save: bool = True,
        run_id: Optional[str] = None,
        resume_from: Optional[str] = None,
        use_multithreading: bool = False
) -> MonoMorph:
    """
    Run MonoMorph refactoring process.

    Required Args:
        app: Application name to refactor
        app_source_code_path: Path to the monolithic application source code
        decomposition_file: Path to decomposition JSON file
        package: Java package name of the application
        java_version: Java version used by the application
        build_tool: Build tool used by the application (maven or gradle)
        original_dockerfile_path: Path to the original Dockerfile for the monolith

    Optional Args:
        refact_approach: Refactoring approach ("ID-only" or "Hybrid", default: "Hybrid")
        refact_model: LLM model for refactoring (default: "gemini-2.5-pro")
        parser_model: LLM model for parsing (default: "ministral-8b")
        decision_model: LLM model for decision making (default: "gemini-2.5-pro")
        correction_model: LLM model for corrections (default: "gemini-2.5-pro")
        fallback_model: Fallback LLM model (default: "gemini-2.5-pro")
        analysis_data_path: Path to analysis data (default: "./data/analysis")
        out_path: Root output path for all generated artifacts (default: "./data/monomorph-output/{app}")
        refactored_code_path: Path to save refactored code (default: "{out_path}/refactored_code")
        llm_response_path: Path for LLM responses (default: "{out_path}/llm_responses")
        llm_checkpoints_path: Path for LLM checkpoints (default: "{out_path}/llm_checkpoints")
        exp_data_path: Path to save experiment metadata (default: {out_path})
        include_tests: Include tests in refactoring (default: False)
        restrictive: Use restrictive mode to exclude ambiguous classes (default: True)
        use_llm_cache: Use LLM cache for reusing prompts (default: True)
        reset_cache: Reset LLM cache before running (default: False)
        llm_cache_path: Path to LLM cache database (default: ".langchain.db")
        checkpoint_load: Load existing checkpoints (default: True)
        checkpoint_save: Save checkpoints during refactoring (default: True)
        run_id: Specific run ID to resume (default: None - generates new ID)
        resume_from: Resume from specific output directory (default: None)
        use_multithreading: Use multithreading for refactoring (default: False)

    Returns:
        MonoMorph instance after refactoring
    """
    # Initialize experiment tracking
    start_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamp_short = datetime.now().strftime('%y%m%d%H%M')
    start_time = time.perf_counter_ns()
    cpu_start_time = time.process_time_ns()

    # Set default paths
    out_path = out_path or os.path.join(os.curdir, "data", "monomorph-output", app)
    refactored_code_path = refactored_code_path or os.path.join(out_path, "refactored_code")
    llm_response_path = llm_response_path or os.path.join(out_path, "llm_responses")
    llm_checkpoints_path = llm_checkpoints_path or os.path.join(out_path, "llm_checkpoints")
    exp_data_path = exp_data_path or out_path

    # Setup logging
    logger, log_file_path = setup_logging(app)

    # Load decomposition
    assert os.path.exists(app_source_code_path), f"Application source code path {app_source_code_path} does not exist"
    assert os.path.exists(decomposition_file), f"Decomposition file path {decomposition_file} does not exist"
    assert os.path.exists(original_dockerfile_path), f"Dockerfile path {original_dockerfile_path} does not exist"
    with open(decomposition_file, "r") as file:
        decomposition_data = json.load(file)
    decomp = Decomposition(
        name=decomposition_data["name"],
        app_name=app,
        partitions=decomposition_data["partitions"],
        language=decomposition_data["language"],
        level=decomposition_data["granularity"]
    )

    # Setup LLM cache
    if use_llm_cache:
        logger.debug("Using LLM cache")
        sqlite_cache = SQLiteCache(database_path=llm_cache_path)
        set_llm_cache(sqlite_cache)
        if reset_cache:
            sqlite_cache.clear()

    # Setup checkpointing
    logger.debug("Setting up checkpointing mechanism")
    checkpoint_config = {
        "path": llm_checkpoints_path,
        "should_load": checkpoint_load,
        "should_save": checkpoint_save
    }

    # Initialize MonoMorph
    logger.info(f"Initializing MonoMorph with app {app} and package {package}")
    id_only = refact_approach == "ID-only"
    mono_refact = MonoMorph(
        app, app_source_code_path, package, decomp, refactored_code_path,
        analysis_data_path,
        refact_model=refact_model,
        parsing_model=parser_model,
        decision_model=decision_model,
        correction_model=correction_model,
        include_tests=include_tests,
        original_dockerfile_path=original_dockerfile_path,
        restrictive_mode=restrictive,
        build_tool=build_tool,
        id_approach_only=id_only,
        llm_response_path=llm_response_path,
        checkpoint_config=checkpoint_config,
        run_id=run_id,
        use_multithreading=use_multithreading,
        fallback_model=fallback_model,
        resume_from=resume_from
    )

    # Start refactoring
    logger.info("Starting refactoring process")
    mono_refact.refactor()
    logger.info("Refactoring process finished successfully")

    # Copy logs to output directory
    logger.info(f"Copying logs to {mono_refact.project.project_path}")
    shutil.copyfile(log_file_path, os.path.join(out_path, "refactoring_logs.log"))

    # Save experiment metadata
    args_namespace = Namespace(
        app=app,
        refact_approach=refact_approach,
        decomposition_file=decomposition_file,
        refact_model=refact_model,
        parser_model=parser_model,
        decision_model=decision_model,
        correction_model=correction_model,
        include_tests=include_tests,
        restrictive=restrictive,
        llm_cache_path=llm_cache_path,
        use_llm_cache=use_llm_cache,
        llm_checkpoints_path=llm_checkpoints_path,
        checkpoint_load=checkpoint_load,
        checkpoint_save=checkpoint_save,
        original_dockerfile_path=original_dockerfile_path,
        app_source_code_path=app_source_code_path,
        package=package,
        java_version=java_version
    )
    save_experiment_metadata(mono_refact, args_namespace, start_time, cpu_start_time, start_timestamp, timestamp_short,
                             exp_data_path)

    logger.info("MonoMorph run finished successfully")

    return mono_refact