{# Jinja2 grpc dto client prompt template #}
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
    dto_name:                       The name of the DTO class.
    id_mapper_class:                The class that contains the mapping logic.
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
#}

### Context

You are tasked with implementing a gRPC client in {{ language.name }} using the DTO (Data Transfer Object) pattern based on a previously generated protobuf service definition. This client will use composition to expose the same API as the original class while enabling seamless microservices communication.

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

### Requirements

#### Core DTO Client Implementation
1. **Composition Pattern**: Use composition to expose getters and setters of the `{{ dto_name }}` class (proto message representing the DTO)
2. **Constructor Compatibility**: Implement constructors with API identical to the original class, adapting them to work with the DTO
3. **Method Implementation**: Implement **only** the methods defined in the generated proto service
4. **DTO Field Management**: Include a private field of type `{{ dto_name }}` for data storage and mapping
5. **DTO Constructor**: Maintain the private constructor that accepts a `{{ dto_name }}` object (enables fromDTO/toDTO methods from template)
6. **API Exposure**: Implement all getters and setters of the DTO class to maintain the same API as the original class
7. **gRPC Integration**: Use the stub instance with host/port values loaded from `ServiceRegistry` using `TARGET_SERVICE_ID` (already implemented in template's `performRpcSetup`)
8. **Template Compliance**: Retain package name and class name from the provided template
9. **Seamless Integration**: Ensure existing code can use the client class without awareness of the refactoring
10. **No Original Class References**: Do not reference the original class (no longer in classpath)

#### Architecture Integration
- **Service Registry**: Uses `ServiceRegistry` for service discovery
- **DTO Mapping**: Built-in `fromDTO()` and `toDTO()` methods for seamless conversion
- **Data Storage**: All data managed through the internal `{{ dto_name }}` field

#### Type Mapping Rules
{% if references_mapping.idbased %}
**ID-based Type Mapping**
Use the `{{ id_mapper_class.full_name }}` utility class for RefactoredObjectID conversions:
- `public static Object fromID(RefactoredObjectID id)`: Converts RefactoredObjectID to original/proxy instance (cast to correct type)
- `public static RefactoredObjectID toID(Object object)`: Converts original/proxy instance to RefactoredObjectID

**Specific ID-based Classes:**
{% for c_name, api_class in references_mapping.idbased.items() %}
{% if api_class.microservice == current_microservice %}
- `{{ c_name }}` ↔ `RefactoredObjectID`
{% else %}
- `{{ api_class.client_name }}` (proxy) ↔ `RefactoredObjectID` (original `{{ c_name }}` not available - DO NOT import)
{% endif %}
{% endfor %}
{% endif %}

{% if references_mapping.dto %}
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

### DTO Pattern Specifics

#### Composition Requirements
- **Data Storage**: All class data stored in private `{{ dto_name }}` field
- **API Delegation**: Getters/setters delegate to the internal DTO object
- **Constructor Adaptation**: Public constructors create and populate the internal DTO
- **Conversion Methods**: Template provides `fromDTO({{ dto_name }})` and `toDTO()` methods

### Validation Checklist
Before finalizing your implementation, ensure:
- [ ] Only methods from the proto service definition are implemented
- [ ] Constructor API matches the original class exactly, adapted for DTO storage
- [ ] All getters/setters from DTO are exposed to maintain original API
- [ ] DTO composition pattern is properly implemented
- [ ] All type mappings follow the specified rules
- [ ] Import statements are complete and correct
- [ ] No references to unavailable original classes
- [ ] Template structure and naming is preserved
- [ ] fromDTO/toDTO methods work correctly with the internal DTO field
