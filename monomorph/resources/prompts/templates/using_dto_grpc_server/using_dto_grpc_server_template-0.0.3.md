{# Jinja2 grpc server prompt template #}
{# Variables:
    proto_prompt:                   The prompt to generate the proto file.
    proto_response:                 The generated proto file.
    language:                       The language to use for the server implementation.
      language.name:                The name of the language.
      language.lowercase:           The lowercase name of the language.
      language.extension:           The file extension of the language. 
    mapper_class:                   The mapper class that translates between DTO and domain objects.
        mapper_class.name:          The name of the mapper class.
        mapper_class.full_name:     The fully qualified name of the mapper class.
        mapper_class.code:          The code of the mapper class.
    id_mapper_class:                The class that contains the mapping logic between RefactoredObjectID and proxy/domain objects.
        mapper_class.full_name:     The qualified name of the id mapper class.
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
#}

### Context

You are tasked with implementing a gRPC server in {{ language.name }} using the DTO (Data Transfer Object) pattern based on a previously generated protobuf service definition. This server will handle DTO-to-domain object mapping and provide seamless microservices communication.

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

{% if mapper_class is not none %}
#### DTO Mapper Class
**File**: {{ mapper_class.name }}.{{ language.extension }}
```{{ language.lowercase }}
{{ mapper_class.code | safe }}
```
{% endif %}

### Requirements

#### Core Server Implementation
1. **Service Implementation**: Implement **only** the services defined in the generated proto file
2. **DTO Mapping Pattern**: Each method must:
   - Start by mapping the DTO to the original domain object using the `{{ mapper_class.name }}` class
   - Perform the business logic on the domain object
   - Map the domain object back to DTO using the `{{ mapper_class.name }}` class (unless the domain object is clearly not updated in the method)
3. **MapStruct Integration**: Use the provided MapStruct mapper interface for all DTO transformations
4. **Template Compliance**: Use package name and class name from the provided template
5. **No Server Exposure**: Do not expose the server (handled in main function later)

#### DTO Transformation Rules
- **Input Processing**: Convert incoming DTOs to domain objects before business logic
- **Output Processing**: Convert domain objects back to DTOs for responses
- **Optimization**: Reuse the same DTO in response if the domain object is clearly not modified
- **Mapper Interface**: Use the provided `{{ mapper_class.name }}` MapStruct mapper

#### Type Mapping Rules
{% if references_mapping.idbased %}
**ID-based Type Mapping**
Some method input/output types are changed to `RefactoredObjectID` in the proto file:
- Types can be original classes or proxy/client classes
- Each proxy/client has the same name as the class it represents
- Use `{{ id_mapper_class.full_name }}` utility class for conversions:
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
- [ ] All methods follow the DTO-to-domain-to-DTO transformation pattern
- [ ] MapStruct mapper is used for all DTO conversions
- [ ] Domain objects are properly converted back to DTOs for responses
- [ ] All type mappings follow the specified rules
- [ ] Import statements are complete and correct
- [ ] No references to unavailable original classes
- [ ] Template structure and naming is preserved
