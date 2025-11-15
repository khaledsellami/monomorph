{# Jinja2 grpc proto prompt template #}
{# Variables:
    language:                       The language to use for the server implementation.
      language.name:                The name of the language.
      language.lowercase:           The lowercase name of the language.
      language.extension:           The file extension of the language. 
    class_:                         The Class object that contains the source code of the class to be refactored.
        class_.name:                The name of the class.
        class_.full_name:           The fully qualified name of the class.
        class_.code:                The code of the class.
    methods:                        The list of methods that are called by external microservices.
    proto_template:                 The template for the protobuf definition.
        server_template.name:       The name of the proto file.
        server_template.code:       The code of the proto template.
    fields:                         The list of fields that should be included in the DTO message.
    shared_proto_package            The package name of the shared proto file that contains the `RefactoredObjectID` message.
    references_mapping:             A dictionary containing information about referenced API classes
        references_mapping.dto:     A dictionary mapping classes that were refactored with the DTO pattern
            c_name:                 The name of the class.
            api_class:              Its metadata class.
                client_name:        The name of the client class.
                dto_name:           The simple name of the DTO class.
                proto_package:      The package name of the DTO class.
                mapper_name:        The fully qualified name of the mapper class.
                proto_filename:     The name of the proto file that contains the DTO class.
        references_mapping.idbased: A dictionary mapping classes that were refactored with the ID pattern (same as above)
#}

### Context

{% if methods|length == 0 %}
You are tasked with creating a protobuf Data Transfer Object (DTO) definition for the {{ language.name }} class `{{ class_.full_name }}`. This class is referenced by external microservices but does not expose any methods, so only the DTO representation is required.
{% else %}
You are tasked with creating a protobuf gRPC service definition with DTO support for the {{ language.name }} class `{{ class_.full_name }}` to enable microservices communication. The class contains methods that need to be exposed as RPC endpoints.
{% endif %}

### Input Data

#### Target Class
**File**: {{ class_.name }}.{{ language.extension }}
```{{ language.lowercase }}
{{ class_.code | safe }}
```

#### Proto Template
**File**: {{ proto_template.name }}.proto
```proto
{{ proto_template.code | safe }}
```

{% if methods|length > 0 %}
#### Methods to Expose
The following methods should be exposed as RPC endpoints (only if they exist in the class):
{% for method in methods %}- `{{ method }}`
{% endfor %}
{% endif %}

{% if fields|length > 0 %}
#### Required DTO Fields
The DTO should include at least the following fields from the class:
{% for field in fields %}- `{{ field }}`
{% endfor %}
{% endif %}

### Requirements

{% set id_refs = references_mapping.idbased|length > 0 %}
{% set dto_refs = references_mapping.dto|length > 0 %}
{% set refs_text = '' %}
{% if id_refs %}
{% set refs_text = refs_text + 'ID' %}
{% endif %}
{% if dto_refs %}
    {% if id_refs %}
    {% set refs_text = refs_text + ' or ' %}
    {% endif %}
{% set refs_text = refs_text + 'DTO' %}
{% endif %}

#### Core Proto File Specifications
1. **DTO Message**: Create a `{{ class_.name }}DTO` message representing the Data Transfer Object for the class
{% if fields|length > 0 %}
2. **Field Mapping**: Include the specified fields and any other necessary fields to represent the class
3. **Field Names**: Retain original field names from source code even if they don't follow protobuf conventions. {% if id_refs or dto_refs %} The exceptions are the fields that are mapped to other {{ refs_text }} classes (see below for details).{% endif %}
{% endif %}
{% if methods|length > 0 %}
4. **Method Exposure**: Include only the methods from the list above that are actually present in the class
5. **Message Design**: Create dedicated request/response messages for all inputs and outputs
6. **DTO Integration**: Each request and response message should include the `{{ class_.name }}DTO` message
{% endif %}
7. **Template Compliance**: Use the exact package and service names from the provided template

#### Type Mapping Rules
{% if references_mapping.idbased %}
- **ID-based classes**: The following classes use `{{ shared_proto_package }}.RefactoredObjectID`:
  {% for c_name, c_api_class in references_mapping.idbased.items() %}
  * `{{ c_name }}`
  {% endfor %}
{% endif %}
{% if references_mapping.dto %}
- **DTO-mapped classes**: Use the specified DTO classes with proper imports:
  {% for c_name, c_api_class in references_mapping.dto.items() %}
  * `{{ c_name }}` → `{{ c_api_class.dto_name }}` (package: `{{ c_api_class.proto_package }}`, file: `{{ c_api_class.proto_filename }}`)
  {% endfor %}
{% endif %}

### Output Format

Structure your response with these exact sections:

#### ## Explanation
1. **Class Analysis**: Describe the class structure and its fields
{% if methods|length > 0 %}
2. **Method Validation**: List which methods from the requested list actually exist in the class
{% endif %}
3. **DTO Design**: Explain how the class will be represented as a DTO message
4. **Type Mapping**: Explain how each field type will be handled in protobuf
{% if methods|length > 0 %}
5. **Message Design**: Justify the structure of request/response messages
{% endif %}
6. **Import Strategy**: Detail which proto files need to be imported and why

#### ## Result
Provide the complete protobuf definition with:
- All necessary imports
- Properly structured DTO message
{% if methods|length > 0 %}
- Service definition with validated methods only
- Complete request/response messages
{% endif %}
- Correct package declaration

#### ## Comments
Include any additional considerations, limitations, or architectural notes.

### Validation Checklist
Before finalizing your response, ensure:
{% if methods|length > 0 %}
- [ ] Only methods from the provided list that exist in the class source code are exposed
{% endif %}
- [ ] DTO message includes all required fields with correct names
- [ ] All type mappings follow the specified rules
- [ ] Import statements are complete and correct
- [ ] Package names match the template exactly