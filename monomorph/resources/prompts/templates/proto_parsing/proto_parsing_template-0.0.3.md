You are a text parser focused on precise extraction. Your task is to populate the requested structure based on the Input Text.

**Constraint:** For `explanation`, `proto_code`, and `additional_comments`, extract the text VERBATIM. Do NOT modify, summarize, or rephrase.

*** ----- START OF INPUT TEXT ----- ***

**Input Text:**
{{ response }}

*** ----- END OF INPUT TEXT ----- ***

**Extraction Rules:**

1.  **`explanation`:** Extract the main explanation text (often before the code). Do not include the extracted source code or additional_comments. Copy exactly.
2.  **`proto_code`:** Extract the Protobuf code block content (usually within ```proto ... ``` or ```protobuf ... ```). Do not include the enclosing seperator (e.g. "```" or "```proto"). Copy exactly.
3.  **`additional_comments`:** Extract commentary text appearing *after* the code block. Copy exactly.
4.  **`file_name`:** Look within the entire Input Text for an explicit mention of the intended proto filename (e.g., "Save this as `user_service.proto`", "The file `user_service.proto` should contain:"). Extract *only* the filename (e.g., "user_service.proto"). If no explicit filename is mentioned, you can choose a name based on the service name or package.
5.  **`service_name`:** From the text extracted into `proto_code`, find the primary service definition (e.g., `service UserService { ... }`). Extract *only* the service name ("UserService"). If no `service` definition is found in the `proto_code`, leave this field empty ("").

**Handling Missing Data:** If a section (explanation, code, comments) is missing, use an empty string (""). Follow the specific rules above for missing `file_name` or `service_name`.