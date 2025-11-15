{# Jinja2 grpc server prompt template #}
{# Variables:
    proto_prompt:                   The prompt to generate the proto file.
    proto_response:                 The generated proto file.
    language:                       The language to use for the server implementation.
      language.name:                The name of the language.
      language.lowercase:           The lowercase name of the language.
      language.extension:           The file extension of the language. 
    class_id_registry_full_name:    The Class that contains the class ID registry details.
    id_class:                       The class that contains the RefactoredObjectID details.
        id_class.name:              The name of the RefactoredObjectID class.
        id_class.full_name:         The fully qualified name of the RefactoredObjectID class.
        id_class.code:              The code of the RefactoredObjectID class.
    mapper_class:                   The class that contains the mapping logic.
        mapper_class.name:          The name of the mapper class.
    server_template:                The template for the server implementation.
        server_template.name:       The name of the server template.
        server_template.code:       The code of the server template.
    references_mapping:             A dictionary containing information about referenced API classes
        references_mapping.dto:     A dictionary mapping classes that were refactored with the DTO pattern
            c_name:                 The name of the class.
            api_class:              Its metadata class.
                client_name:        The name of the client class.
                dto_name:           The simple name of the DTO class.
                proto_package:      The package name of the DTO class.
                mapper_name:        The fully qualified name of the mapper class.
        references_mapping.idbased: A dictionary mapping classes that were refactored with the ID pattern (same as above)
    current_microservice:           The microservice of the current class
    id_only:                        A boolean indicating if ID only approach is used (for backwards compatibility)
#}

### Context

You are tasked with implementing a gRPC server in {{ language.name }} based on a previously generated protobuf service definition. This server will manage object instances through ID-based mapping and provide seamless microservices communication.

### Previous Generation Context

#### Initial Proto Generation Request
{{ proto_prompt }}

#### Generated Proto Service
{{ proto_response }}

### Input Data

#### Server Template
**File**: {{ server_template.name }}.{{ language.extension }}
```{{ language.lowercase }}
{{ server_template.code | safe }}
```

{% if id_class is not none %}
#### RefactoredObjectID Definition
**File**: shared.proto
```proto
{{ id_class.code | safe }}
```
{% endif %}

### Requirements

#### Core Server Implementation
1. **Service Implementation**: Implement **only** the services defined in the generated proto file
2. **Method Pattern**: Each non-static, non-constructor method must:
   - Retrieve the instance using the provided ID
   - Call the actual method from the original class (as shown in template example)
3. **Constructor Implementation** (`createObject`):
   - Create new instance (or retrieve singleton if applicable)
   - Generate unique instance ID using UUID-like approach
   - Register ID-instance pair with lease manager
   - Return `RefactoredObjectID` with classID, instanceID, and serviceID
4. **Template Compliance**: Use package name and class name from the provided template
5. **No Server Exposure**: Do not expose the server (handled in main function later)
6. **Complete Constructor Logic**: Add missing argument mapping logic to the `createObject` RPC method

#### Instance Management
- **Class ID**: Obtain static class ID from `{{ class_id_registry_full_name }}` utility class
- **Instance ID**: Generate using UUID-like approach for each new instance
- **Singleton Handling**: If original class is singleton:
  - Look for existing singleton instance
  - Return same instanceID for each call
  - Implement this logic only if the original class is actually a singleton

#### Type Mapping Rules
{% if references_mapping.idbased or id_only %}
**ID-based Type Mapping**
Some method input/output types are changed to `RefactoredObjectID` in the proto file.
- Types can be original classes or proxy/client classes
- Each proxy/client has the same name as the class it represents
- Use `{{ mapper_class.full_name }}` utility class for conversions:
  - `public static Object fromID(RefactoredObjectID id)`: Converts RefactoredObjectID to original/proxy instance (cast to correct type)
  - `public static RefactoredObjectID toID(Object object)`: Converts original/proxy instance to RefactoredObjectID

{% if not id_only %}
**Specific ID-based Classes:**
{% for c_name, api_class in references_mapping.idbased.items() %}
{% if api_class.microservice == current_microservice %}
- `{{ c_name }}` ↔ `RefactoredObjectID`
{% else %}
- `{{ api_class.client_name }}` (proxy) ↔ `RefactoredObjectID` (original `{{ c_name }}` not available - DO NOT import)
{% endif %}
{% endfor %}
{% endif %}
{% endif %}

{% if references_mapping.dto and not id_only %}
**DTO Type Mapping**
Some input/output types are changed to DTO classes in the proto file:
{% for c_name, api_class in references_mapping.dto.items() %}
{% if api_class.microservice == current_microservice %}
{% set mapper_simple_name = api_class.mapper_name.split('.')[-1] %}
- `{{ c_name }}` ↔ `{{ api_class.dto_name }}` (package: `{{ api_class.proto_package }}`)
  - Use `{{ mapper_simple_name }}.INSTANCE.toDTO()` and `{{ mapper_simple_name }}.INSTANCE.fromDTO()`
{% else %}
- `{{ api_class.client_name }}` (proxy) ↔ `{{ api_class.dto_name }}` (package: `{{ api_class.proto_package }}`)
  - Use `toDTO()` method and `fromDTO()` static method from `{{ api_class.client_name }}`
  - Original `{{ c_name }}` not available - DO NOT import
{% endif %}
{% endfor %}
{% endif %}

### Validation Checklist
Before finalizing your implementation, ensure:
- [ ] Only services from the proto definition are implemented
- [ ] All methods follow the ID-retrieval-then-call pattern
- [ ] Constructor creates instances and manages ID registration properly
- [ ] Singleton logic is implemented only if the original class is singleton
- [ ] All type mappings follow the specified rules
- [ ] Import statements are complete and correct
- [ ] No references to unavailable original classes
- [ ] Template structure and naming is preserved
