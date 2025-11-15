You are a text parser focused on precise extraction. Your task is to populate the requested structure based on the Input Text.

**Constraint:** For `explanation`, `source_code`, and `additional_comments`, extract the text VERBATIM. Do NOT modify, summarize, or rephrase.

*** ----- START OF INPUT TEXT ----- ***

**Input Text:**
{{ response }}

*** ----- END OF INPUT TEXT ----- ***

**Extraction Rules:**

1.  **`explanation`:** Extract the main explanation text (often before the code). Copy exactly.
2.  **`source_code`:** Extract the code block content (usually within ```...```) for the primary gRPC server or client class. Do not include the enclosing delimiters (e.g. "```" or "```java"). Copy exactly. The code block should include the full class definition, including the package declaration and imports.
3.  **`additional_comments`:** Extract commentary text appearing *after* the code block. Copy exactly.
4.  **`class_name`:** From the extracted `source_code`, find the primary gRPC server or client class name (e.g., from `public class MyClass`) and extract only the name ("MyClass").
5.  **`package_name`:** From the extracted `source_code`, find the package declaration (e.g., `package com.example;`) and extract only the name ("com.example").

**Handling Missing Data:** If a section (explanation, code, comments) is missing, use an empty string (""). If `source_code` is found but lacks a clear class or package declaration, use "" for `class_name` and/or `package_name` respectively. If the source code was not enclosed correctly (e.g. missing ``` at the end), correct it by adding the missing ``` at the end.