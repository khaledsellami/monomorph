from main import run_monomorph


def example():
    """
    Example usage of MonoMorph on a sample application.

    This function demonstrates how to use the run_monomorph API directly.
    """
    app = "spring-petclinic"
    package = "org.springframework.samples.petclinic"
    build_tool = "maven"
    java_version = "17"

    # Run MonoMorph on the application
    mono_refact = run_monomorph(
        app=app,
        app_source_code_path=f"./examples/{app}/monolithic-source-code",
        decomposition_file=f"./examples/{app}/decomposition_with_tests.json",
        package=package,
        java_version=java_version,
        build_tool=build_tool,
        original_dockerfile_path=f"./examples/{app}/Dockerfile",
        refact_approach="Hybrid",
        refact_model="mm_google/gemini-2.5-flash::low",
        parser_model="mm_google/gemini-2.5-flash::low",
        decision_model="mm_google/gemini-2.5-flash::low",
        correction_model="mm_google/gemini-2.5-flash::low",
        fallback_model="mm_google/gemini-2.5-flash::low",
        include_tests=False,
        restrictive=True,
        use_llm_cache=True,
        reset_cache=False,
        use_multithreading=True
    )
    return mono_refact


if __name__ == "__main__":
    example()
