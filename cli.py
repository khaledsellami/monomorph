import argparse
import os

from main import run_monomorph


def cli():
    parser = argparse.ArgumentParser(
        description="MonoMorph: Automated Monolith-to-Microservices Refactoring Tool"
    )

    # Required arguments
    parser.add_argument("--app", required=True,
                        help="Application name to refactor")
    parser.add_argument("--app-source-code-path", required=True,
                        help="Path to the monolithic application source code")
    parser.add_argument("--decomposition-file", required=True,
                        help="Path to decomposition JSON file")
    parser.add_argument("--package", required=True,
                        help="Java package name of the application")
    parser.add_argument("--java-version", required=True,
                        help="Java version used by the application")
    parser.add_argument("--build-tool", required=True, choices=["maven", "gradle"],
                        help="Build tool used by the application")
    parser.add_argument("--original-dockerfile-path", required=True,
                        help="Path to the original Dockerfile for the monolith")

    # Refactoring approach
    parser.add_argument("--refact-approach", choices=["ID-only", "Hybrid"], default="Hybrid",
                        help="Refactoring approach (default: Hybrid)")

    # LLM models
    parser.add_argument("--refact-model", default="gemini-2.5-pro",
                        help="LLM model for refactoring (default: gemini-2.5-pro)")
    parser.add_argument("--parser-model", default="ministral-8b",
                        help="LLM model for parsing (default: ministral-8b)")
    parser.add_argument("--decision-model", default="gemini-2.5-pro",
                        help="LLM model for decision making (default: gemini-2.5-pro)")
    parser.add_argument("--correction-model", default="gemini-2.5-pro",
                        help="LLM model for corrections (default: gemini-2.5-pro)")
    parser.add_argument("--fallback-model", default="gemini-2.5-pro",
                        help="Fallback LLM model (default: gemini-2.5-pro)")

    # Output paths
    parser.add_argument("--analysis-data-path", default=os.path.join(os.curdir, "data", "analysis"),
                        help="Path to analysis data (default: ./data/analysis)")
    parser.add_argument("--out-path", default=None,
                        help="Root output path for all artifacts (default: ./data/monomorph-output/{app})")
    parser.add_argument("--refactored-code-path", default=None,
                        help="Path to save refactored code (default: {out_path}/refactored_code)")
    parser.add_argument("--llm-response-path", default=None,
                        help="Path for LLM responses (default: {out_path}/llm_responses)")
    parser.add_argument("--llm-checkpoints-path", default=None,
                        help="Path for LLM checkpoints (default: {out_path}/llm_checkpoints)")
    parser.add_argument("--exp-data-path", default=None,
                        help="Path to save experiment metadata (default: {out_path})")

    # Refactoring options
    parser.add_argument("--include-tests", action="store_true", default=False,
                        help="Include tests in refactoring (default: False)")
    parser.add_argument("--restrictive", action="store_true", default=True,
                        help="Use restrictive mode to exclude ambiguous classes (default: True)")
    parser.add_argument("--no-restrictive", action="store_false", dest="restrictive",
                        help="Disable restrictive mode")

    # LLM cache
    parser.add_argument("--use-llm-cache", action="store_true", default=True,
                        help="Use LLM cache for reusing prompts (default: True)")
    parser.add_argument("--no-llm-cache", action="store_false", dest="use_llm_cache",
                        help="Disable LLM cache")
    parser.add_argument("--reset-cache", action="store_true", default=False,
                        help="Reset LLM cache before running (default: False)")
    parser.add_argument("--llm-cache-path", default=".langchain.db",
                        help="Path to LLM cache database (default: .langchain.db)")

    # Checkpointing
    parser.add_argument("--checkpoint-load", action="store_true", default=True,
                        help="Load existing checkpoints (default: True)")
    parser.add_argument("--no-checkpoint-load", action="store_false", dest="checkpoint_load",
                        help="Don't load existing checkpoints")
    parser.add_argument("--checkpoint-save", action="store_true", default=True,
                        help="Save checkpoints during refactoring (default: True)")
    parser.add_argument("--no-checkpoint-save", action="store_false", dest="checkpoint_save",
                        help="Don't save checkpoints")

    # Advanced options
    parser.add_argument("--run-id", type=str, default=None,
                        help="Specific run ID to resume (default: generates new ID)")
    parser.add_argument("--resume-from", type=str, default=None,
                        help="Resume from specific output directory (default: None)")
    parser.add_argument("--use-multithreading", action="store_true", default=False,
                        help="Use multithreading for refactoring (default: False)")

    args = parser.parse_args()

    # Call the main run function with parsed arguments
    run_monomorph(
        app=args.app,
        app_source_code_path=args.app_source_code_path,
        decomposition_file=args.decomposition_file,
        package=args.package,
        java_version=args.java_version,
        build_tool=args.build_tool,
        original_dockerfile_path=args.original_dockerfile_path,
        refact_approach=args.refact_approach,
        refact_model=args.refact_model,
        parser_model=args.parser_model,
        decision_model=args.decision_model,
        correction_model=args.correction_model,
        fallback_model=args.fallback_model,
        analysis_data_path=args.analysis_data_path,
        out_path=args.out_path,
        refactored_code_path=args.refactored_code_path,
        llm_response_path=args.llm_response_path,
        llm_checkpoints_path=args.llm_checkpoints_path,
        exp_data_path=args.exp_data_path,
        include_tests=args.include_tests,
        restrictive=args.restrictive,
        use_llm_cache=args.use_llm_cache,
        reset_cache=args.reset_cache,
        llm_cache_path=args.llm_cache_path,
        checkpoint_load=args.checkpoint_load,
        checkpoint_save=args.checkpoint_save,
        run_id=args.run_id,
        resume_from=args.resume_from,
        use_multithreading=args.use_multithreading
    )


if __name__ == "__main__":
    cli()
