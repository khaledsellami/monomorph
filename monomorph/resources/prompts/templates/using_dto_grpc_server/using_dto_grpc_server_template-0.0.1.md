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
        mapper_class.name:          The name of the id mapper class.
    server_template:                The template for the server implementation.
        server_template.name:       The name of the server template.
        server_template.code:       The code of the server template.
#}
# Initial instructions
{{ proto_prompt }}

# Developer Response
{{ proto_response }}

# Follow-up instructions
With the proto file created, you will now need to create the server implementation of the gRPC service in {{ language.name }} using the given template as a basis.
## Instructions
### Implement the server which:
- Implements each service in the proto file. 
- Each method starts by mapping the DTO to the original domain object using the `{{ mapper_class.name }}` class. It is a mapstruct mapper and its interface is shown below.
- Each method should map the domain object back to the DTO using the `{{ mapper_class.name }}` class unless the domain object is clearly not updated in the corresponding method (in that case, the same DTO can be used in the response).
- Does not expose the server yet since that will be done in the main function later.
{% if id_mapper_class is not none %}
- Some method input and output types have been changed to `RefactoredObjectID` in the proto file.  
  - The types can be a class from the original code or a proxy/client of the class.
  - Each proxy/client will have the same name as the class it represents. 
  - Mapping between `RefactoredObjectID` and the original/proxy class instance should be done using the `{{ mapper_class.full_name }}` utility class. It exposes the static methods `fromID` and `toID` to convert between the two types. Its api is:
    - `public static Object fromID(RefactoredObjectID id)`: Converts a `RefactoredObjectID` to the original or proxy class instance.
    - `public static RefactoredObjectID toID(Object object)`: Converts an original or proxy class instance to a `RefactoredObjectID`.
{% endif %}
- The package name and the class name of the server class defined in the template should be used.

{% if mapper_class is not none %}
## {{ mapper_class.name }}
##### {{ mapper_class.name }}.{{ language.extension }}
```{{ language.lowercase }}
{{ mapper_class.code | safe }}
```
{% endif %}

## Template
##### {{ server_template.name }}.{{ language.extension }}
```{{ language.lowercase }}
{{ server_template.code | safe }}
```
