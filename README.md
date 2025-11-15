<a name="readme-top"></a>

<h3 align="center">MonoMorph</h3>

<p>
    <div align="center">
        This project is an implementation of an extended version of the automated refactoring approach described in: 
        <ul align="center">
          <li><a href="https://doi.org/10.1109/QRS65678.2025.00018">Beyond Decomposition: A LLM-Powered Automated Approach to Refactoring Monoliths Into Microservices</a></li>
        </ul>
    </div>
</p>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#what-it-does">What It Does</a></li>
        <li><a href="#technologies--techniques">Technologies & Techniques</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li>
      <a href="#usage">Usage</a>
      <ul>
        <li><a href="#preparing-the-input-data">Preparing the input data</a></li>
        <li><a href="#refactoring-the-monolithic-application">Refactoring the monolithic application</a></li>
      </ul>
    </li>
    <li>
      <a href="#advanced-usage">Advanced usage</a>
      <ul>
        <li><a href="#configuration-options">Configuration options</a></li>
      </ul>
    </li>
    <li><a href="#example-application">Example Application</a></li>
    <li><a href="#authors">Authors</a></li>
    <li><a href="#version-history">Version History</a></li>
    <li><a href="#citation">Citation</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#references">References</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->
# About The Project

MonoMorph is a fully automated refactoring tool that transforms monolithic Java applications into microservice architectures. Built on research from "Beyond Decomposition: A LLM-Powered Automated Approach to Refactoring Monoliths Into Microservices" [[1]](#1), it bridges the gap between decomposition planning and executable microservices.

Its main objective is to replace the (previously) local interactions between classes with remote procedure calls (gRPC) while ensuring the consistency and correctness of the newly generated microservices.

## What It Does

Given your monolithic Java application and a decomposition plan, MonoMorph automatically:
- Analyzes your codebase to identify cross-service dependencies
- Determines the optimal refactoring strategy for each API class
- Generates gRPC-based communication infrastructure that replace local calls
- Creates independently deployable microservices
- Validates and corrects compilation errors

## Technologies & Techniques

MonoMorph automates refactoring through a multi-stage workflow powered by specialized AI agents:

1. **Static Analysis** - Analyzes the monolith using INRIA's Spoon to extract class relationships and dependencies
2. **Decision Making** - LLM-powered agent determines the optimal refactoring approach (ID-based or DTO-based) for each API class using structured outputs
3. **Code Generation** - Generates gRPC communication infrastructure with template-based prompting for consistency
4. **Validation & Correction** - Compiles code in isolated Docker containers, with multi-turn LLM correction workflows and conversation rolling summaries to fix errors

**Key Technologies**: LangChain, LangGraph, Pydantic, Docker, gRPC, Protocol Buffers, Spoon


# Getting Started

## Prerequisites

The main requirements are:
* Python 3.12 or higher
* Java Development Kit (JDK) 17 
* Docker or a compatible containerization tool (e.g Podman, Orbstack)
* LLM API access (Openrouter, OpenAI, Google Gemini, or compatible providers)

**Note**: Currently, MonoMorph supports only Java applications built with Maven or Gradle.

## Installation

1. Clone the repo
   ```sh
   git clone https://github.com/khaledsellami/monomorph.git
   ```
2. Install MonoMorph as a Python module:
   ```sh
   cd monomorph/
   pip install -e .
   ```
3. Set up your LLM API credentials in a `.env` file or export them as environment variables:
   ```sh
   export OPENROUTER_API_KEY="your-openrouter-api-key"
   # or
   export GEMINI_API_KEY="your-google-api-key"
   ```

<!-- USAGE EXAMPLES -->
# Usage

## Preparing the input data

MonoMorph requires the following inputs to perform automated refactoring:

### 1. Monolithic Application Source Code
The complete source code of your monolithic Java application. MonoMorph will automatically perform static analysis on the source code to extract structural dependencies and relationships.

```text
your_monolith/
├── src/
│   ├── main/
│   │   └── java/
│   │       └── com/
│   │           └── example/
│   │               ├── User.java
│   │               ├── Order.java
│   │               └── ...
│   └── test/
│       └── ...
├── pom.xml (for Maven)
└── build.gradle (for Gradle)
```

### 2. Decomposition Plan
A JSON file describing how you want to split the monolith into microservices. This file specifies which classes belong to which microservice.

```json
{
  "name": "my_decomposition",
  "language": "java",
  "granularity": "class",
  "partitions": [
    {
      "name": "UserService",
      "classes": ["com.example.User", "com.example.UserRepository"]
    },
    {
      "name": "OrderService",
      "classes": ["com.example.Order", "com.example.OrderRepository"]
    }
  ]
}
```

### 3. Dockerfile Template
A Dockerfile (or reference Dockerfile from your monolith) that specifies the base image used to compile your application. MonoMorph uses this to understand the build environment and dependencies.

**Example:**
```dockerfile
FROM maven:3.8.5-openjdk-17
WORKDIR /app
# MonoMorph only needs the base image specification
# The rest of the Dockerfile is not required
```

## Refactoring the monolithic application

### Using the main.py script

```python
from main import run_monomorph

# Run the refactoring process
monomorph_instance = run_monomorph(
    app="MyApp",
    app_source_code_path="/path/to/monolith/src",
    decomposition_file="/path/to/decomposition.json",
    package="com.example",
    java_version="11", # your Java version
    build_tool="maven", # or "gradle"
    original_dockerfile_path="/path/to/Dockerfile",
    out_path="./output"
)
```

### Key Parameters

- **Required**:
  - `app`: Application name
  - `app_source_code_path`: Path to monolith source code
  - `decomposition_file`: Path to decomposition JSON
  - `package`: Your application's Java package name
  - `java_version`: Your application's Java version
  - `build_tool`: "maven" or "gradle"
  - `original_dockerfile_path`: Path to the Dockerfile example

- **Optional**:
  - `out_path`: Output directory to save refactored microservices and other artifacts (default: "./data/monomorph-output")
  - `refact_approach`: "Hybrid" (default) or "ID-only"
  - `refact_model`: LLM for code generation agent (default: "gemini-2.5-pro")
  - `decision_model`: LLM for decision (ID or DTO) making agent (default: "gemini-2.5-pro")
  - `correction_model`: LLM for error correction agent (default: "gemini-2.5-pro")

### Output Structure

The refactored output will be generated in the following structure:
```text
{out_path}/
└── MyApp/
    ├── refactored_code/
    │   └── MyApp-{timestamp}-{run_id}/
    │       ├── UserService/
    │       │   ├── src/
    │       │   ├── pom.xml
    │       │   └── REFACTORING_REPORT.md
    │       ├── OrderService/
    │       │   ├── src/
    │       │   ├── pom.xml
    │       │   └── REFACTORING_REPORT.md
    │       └── REFACTORING_REPORT.md
    ├── llm_responses/
    ├── llm_checkpoints/
    ├── refactoring_logs.log
    └── metadata.json
```

# Advanced usage

## Configuration options

### LLM Caching and Checkpointing
Enable caching and checkpointing to reuse LLM responses and reduce costs (useful for experiments and debugging):
```python
run_monomorph(
    # ...other params...
    use_llm_cache=True,
    llm_cache_path=".langchain.db",
    checkpoint_load=True,
    checkpoint_save=True,
    llm_checkpoints_path="./checkpoints",
    run_id="specific-run-id"  # Resume specific run
)
```

### Model Selection
Choose different LLMs for different tasks:
```python
run_monomorph(
    # ...other params...
    refact_model="gemini-2.5-pro",      # Code generation
    parser_model="ministral-8b",         # Response parsing
    decision_model="gemini-2.5-pro",     # Decision making
    correction_model="gemini-2.5-pro",   # Error correction
    fallback_model="gemini-2.5-pro"      # Fallback option (in case of rate limits or errors)
)
```

# Example Application
An example monolithic Java application along with a sample decomposition plan and Dockerfile template can be found in the `examples/` directory of this repository. You can use this example to test and explore MonoMorph's capabilities.

## Clone the sample application
Make sure to clone the following specific commit of the repository to ensure compatibility with the decomposition file:
```sh
mkdir -p ./examples/spring-petclinic
git clone https://github.com/spring-projects/spring-petclinic.git
mv spring-petclinic ./examples/spring-petclinic/monolithic-source-code
cd examples/spring-petclinic/monolithic-source-code
git reset --hard 1079767adc4576db0804c6d615c209c3d1cf351f
git clean -df
```

## Run the example script
```sh
python example.py
```


<!-- AUTHORS -->
# Authors

Khaled Sellami - [khaledsellami](https://github.com/khaledsellami) - khaled.sellami.1@ulaval.ca

<!-- VERSION -->
# Version History

* 0.2.0
    * Initial Public Release

<!-- CITATION -->
# Citation
If this work was useful for your research, please consider citing it:
```bibtex
@INPROCEEDINGS{monomorph,
  author={Sellami, Khaled and Jebbar, Oussama and Gannoun, Ayyoub and Saied, Mohamed Aymen},
  booktitle={2025 25th International Conference on Software Quality, Reliability and Security (QRS)}, 
  title={Beyond Decomposition: A LLM-Powered Automated Approach to Refactoring Monoliths Into Microservices}, 
  year={2025},
  volume={},
  number={},
  pages={68-77},
  keywords={Codes;Large language models;Source coding;Microservice architectures;Software quality;Benchmark testing;Reliability engineering;Software reliability;Complexity theory;Contracts;Microservices Migration;Refactoring;Decomposition;Large Language Models;Remote Procedural Calls},
  doi={10.1109/QRS65678.2025.00018}
}

```

<!-- LICENSE -->
# License

TODO

<!-- REFERENCES -->
# References

<a id="1">[1]</a> 
Sellami, Khaled, Oussama Jebbar, Ayyoub Gannoun, and Mohamed Aymen Saied. 'Beyond Decomposition: A LLM-Powered Automated Approach to Refactoring Monoliths Into Microservices'. In 2025 25th International Conference on Software Quality, Reliability and Security (QRS), 68-77, 2025. https://doi.org/10.1109/QRS65678.2025.00018.

<p align="right">(<a href="#readme-top">back to top</a>)</p>
