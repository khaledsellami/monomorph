{# Jinja2 analyze compilation errors prompt template #}
{# Variables:
    language:                       The language to use for the client implementation.
      language.name:                The name of the language.
      language.lowercase:           The lowercase name of the language.
      language.extension:           The file extension of the language. 
    target_microservice:            The name of the microservice that is being compiled.
    new_classes_description:        The pattern to identify the newly generated files/classes.
    compilation_logs:               The compilation logs of the target microservice.
#}
# Instructions
You are working on a {{ language.name }} application that has been refactored into microservices. Each relevant inter-service communication has been wrapped in a gRPC service and client.

Most recently, You were working on the validation of the newly developed code. You have attempted to compile the `{{ target_microservice }}` microservice, but it failed due to compilation errors. Your current task is to analyze the compilation logs, identify the root errors, and think of the necessary changes to fix them.

A root error represents the group of errors showcased in the logs that have a single root cause. For each identified root error, you have to provide:
- The root error description.
- The logs subsection that corresponds to the error, represented as the starting and ending line numbers of the logs.
- A detailed description of the necessary changes to fix the error.
- The names of the relevant classes and/or files that need to be changed. Keep in mind that the changes are exclusively related to the newly generated code (identified by {{ new_classes_description }}. All of the code and artifacts from the original application and from the dependencies have been thoroughly tested and are not the source of the compilation errors.

In order to help you with the task, you will be provided with 
- The relevant compilation logs of the `{{ target_microservice }}` microservice where each line is prefixed with its line number (L[line_num]). 
- A set of tools to acquire additional information if needed:
  - `get_file_content(file_path)`: Returns the content of the file with the given path.
  - `is_new_file(file_path)`: Returns true if the file is a newly generated file, false otherwise.
  - `get_additional_logs(start_line, end_line)`: Returns the additional logs between the given start and end line numbers if available.
  - `get_source_code(class_fqn)`: Returns the source code of the class with the given fully qualified name.

# Compilation Logs
```text
{{ compilation_logs | safe }}
```
