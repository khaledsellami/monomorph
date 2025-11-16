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
    id_only:                        A boolean indicating whether the refactored classes are only represented by their ID.
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

You are tasked with creating a protobuf gRPC service definition for the {{ language.name }} class `{{ class_.full_name }}` to enable microservices communication. The class contains methods that need to be exposed as RPC endpoints.

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

#### Methods to Expose
The following methods should be exposed as RPC endpoints (only if they exist in the class):
{% for method in methods %}- `{{ method }}`
{% endfor %}

### Requirements

#### Core Proto File Specifications
1. **Method Exposure**: Include only the methods from the list above that are actually present in the class
2. **Constructor Wrapper**: Implement the `createObject` RPC from the template as a constructor wrapper
3. **Constructor Args**: Update the `ConstructorArgs` message to match the actual constructor parameters
4. **Message Design**: Create dedicated request/response messages for all inputs and outputs
5. **ID Integration**: Each request message (except `CreateObjectRequest`) must include a `RefactoredObjectID` field
6. **Template Compliance**: Use the exact package and service names from the provided template
7. **Shared Proto**: Use `RefactoredObjectID` from `{{ shared_proto_package }}` package (do not redefine)

#### Type Mapping Rules
{% if id_only %}
- **Non-primitive types**: Replace with `{{ shared_proto_package }}.RefactoredObjectID`
- **Primitive types**: Map directly to protobuf equivalents
{% else %} 
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
{% endif %}

### Output Format

Structure your response with these exact sections:

#### ## Explanation
1. **Method Validation**: List which methods from the requested list actually exist in the class
2. **Constructor Analysis**: Describe the constructor parameters and how they map to `ConstructorArgs`
3. **Type Mapping**: Explain how each input/output type will be handled in protobuf
4. **Message Design**: Justify the structure of request/response messages
5. **Import Strategy**: Detail which proto files need to be imported and why

#### ## Result
Provide the complete protobuf service definition with:
- All necessary imports
- Properly structured messages
- Service definition with validated methods only
- Correct package declaration

#### ## Comments
Include any additional considerations, limitations, or architectural notes.

### Validation Checklist
Before finalizing your response, ensure:
- [ ] Only methods from the provided list that exist in the class source code are exposed
- [ ] Constructor parameters match the actual class constructor
- [ ] All type mappings follow the specified rules
- [ ] Import statements are complete and correct
