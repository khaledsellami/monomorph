{# Jinja2 grpc client prompt template #}
{# Variables:
    proto_prompt:                   The prompt to generate the proto file.
    proto_response:                 The generated proto file.
    language:                       The language to use for the client implementation.
      language.name:                The name of the language.
      language.lowercase:           The lowercase name of the language.
      language.extension:           The file extension of the language. 
    client_template:                The template for the client implementation.
        client_template.name:       The name of the client template.
        client_template.code:       The code of the client template.
    id_class:                       The class that contains the RefactoredObjectID details.
        id_class.name:              The name of the RefactoredObjectID class.
        id_class.full_name:         The fully qualified name of the RefactoredObjectID class.
        id_class.code:              The code of the RefactoredObjectID class.
    mapper_class:                   The class that contains the mapping logic.
        mapper_class.name:          The name of the mapper class.
        mapper_class.full_name:     The fully qualified name of the mapper class.
    references_mapping:             A dictionary containing information about referenced API classes
        references_mapping.dto:     A dictionary mapping classes that were refactored with the DTO pattern
            c_name:                 The name of the class.
            api_class:              Its metadata class.
                client_name:        The name of the client class.
                dto_name:           The simple name of the DTO class.
                proto_package:      The package name of the DTO class.
                mapper_name:        The fully qualified name of the mapper class.
        references_mapping.idbased: A dictionary mapping classes that were refactored with the ID pattern (same as above)
    current_microservice:           The microservice the client class will be implemented in.
    id_only:                        A boolean indicating if ID only approach is used (for backwards compatibility)
#}

### Context

You are tasked with implementing a gRPC client in {{ language.name }} based on a previously generated protobuf service definition. This client will enable seamless microservices communication while maintaining backward compatibility with existing code.

### Previous Generation Context

#### Initial Proto Generation Request
{{ proto_prompt }}

#### Generated Proto Service
{{ proto_response }}

### Input Data

#### Client Template
**File**: {{ client_template.name }}.{{ language.extension }}
```{{ language.lowercase }}
{{ client_template.code | safe }}
```

{% if id_class is not none %}
#### RefactoredObjectID Definition
**File**: shared.proto
```proto
{{ id_class.code | safe }}
```
{% endif %}

### Requirements

#### Core Client Implementation
1. **Constructor Compatibility**: Implement constructors with API identical to the original class using the provided template blueprint
2. **Special Constructor**: Maintain the private constructor that accepts a RefactoredObjectID object
3. **Method Implementation**: Implement **only** the methods defined in the generated proto service (do not implement `createObject` directly - it should be called in `performRemoteCreateAndGetId`)
4. **gRPC Integration**: Use the stub instance with host/port values loaded from `ServiceRegistry` using `TARGET_SERVICE_ID` (already implemented in template's `performRpcSetup`)
5. **Template Compliance**: Retain package name and class name from the provided template
6. **Seamless Integration**: Ensure existing code can use the client class without awareness of the refactoring
7. **No Original Class References**: Do not reference the original class (no longer in classpath)
8. **Complete Implementation**: Properly implement any incomplete methods in the template

#### Architecture Integration
- **Parent Class**: Inherits from `AbstractRefactoredClient` with fields:
  - `protected final String clientId;`
  - `protected final RefactoredObjectID objectId;`
- **Service Registry**: Uses `ServiceRegistry` for service discovery
- **ID Management**: Client instance ID handling is managed by parent class

#### Type Mapping Rules
{% if references_mapping.idbased or id_only %}
**ID-based Type Mapping**
Use the `{{ mapper_class.full_name }}` utility class for RefactoredObjectID conversions:
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
Map between original classes and their DTO equivalents:
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
- [ ] Only methods from the proto service definition are implemented
- [ ] Constructor API matches the original class exactly
- [ ] All type mappings follow the specified rules
- [ ] Import statements are complete and correct
- [ ] No references to unavailable original classes
- [ ] Template structure and naming is preserved
