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
    id_mapper_class:                   The class that contains the mapping logic.
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
# Initial instructions
{{ proto_prompt }}

# Developer Response
{{ proto_response }}

# Follow-up instructions
With the proto file created, you will now need to create the client implementation of the gRPC client in {{ language.name }}. You can use the given template as a basis.
## Instructions
### Implement the client which:
- Uses composition to Expose the getters and setter of the `{{ dto_name }}` class (the proto message that represents the DTO of the domain object `{{ client_template.name }}`).
- Must have constructors with an API identical to the original class. Make sure to match the original class arguments and to add any additional constructors if needed. Adapt the constructor to the DTO. 
- Must implement all the methods in the proto file.
- Has a private field of type `{{ dto_name }}` that represents the DTO object. This field should be used to store the data of the class and to map between the original class and the DTO class.
- Has a private constructor that takes a `{{ dto_name }}` object as an argument. This constructor enables the static fromDTO method to create an instance of the client class from a `{{ dto_name }}` object. It has a toDTO method as well to convert the client class instance to a `{{ dto_name }}` object. These methods are implemented in the template.
- Implements all of the getters and setters of the DTO class enabling the same API as the original class.
- Must have a stub instance to connect to the corresponding server. The host and port values for the stub are loaded from the `ServiceRegistry` class using the value of `TARGET_SERVICE_ID` as a key. This step is already implemented in the template in the method `performRpcSetup`.
- The refactoring must remain seamless for the rest of the classes. It means that all classes that interact with instances of the original class `{{ client_template.name }}` should not be aware of the refactoring and will call the new client class `{{ client_template.name }}` as if it were the original class.
- The package name and the class name of the new client class should be retained from the template.
{# Class mapping section #}
{% if references_mapping.idbased %}
- If an argument or return type in the original methods corresponds to `RefactoredObjectID` in the proto file, the client must map between the two types. For this reason we provide the `{{ id_mapper_class.full_name }}` utility class. It exposes the static methods `fromID` and `toID` to convert between the two types. Its api is:
  - `public static Object fromID(RefactoredObjectID id)`: Converts a `RefactoredObjectID` to the original or proxy class instance. Make sure to cast the result to the correct type.
  - `public static RefactoredObjectID toID(Object object)`: Converts an original or proxy class instance to a `RefactoredObjectID`.
  - The relevant classes are: 
    {% for c_name, api_class in references_mapping.idbased.items() %}
      {% if api_class.microservice == current_microservice %}
    * `{{ c_name }}` should be mapped to/from  `RefactoredObjectID`
      {% else %}
    * The client/proxy `{{ api_class.client_name }}` should be mapped to/from `RefactoredObjectID` instead of the original class `{{ c_name }}` (which is no longer available). DO NOT import `{{ c_name }}`.
      {% endif %}
    {% endfor %}
{% endif %}
{% if references_mapping.dto %}
- Some input or output types have been changed to DTO classes in the proto file. Make sure to import the proper classes in your implementation:
  {% for c_name, api_class in references_mapping.dto.items() %}
    {% if api_class.microservice == current_microservice %}
      {% set mapper_simple_name = api_class.mapper_name.split('.')[-1] %}
  * `{{ c_name }}` should be mapped to/from  `{{ api_class.dto_name }}` (defined within the protobuf package `{{ api_class.proto_package }}`) using its `{{ api_class.mapper_name }}` mapper class (e.g. `{{ mapper_simple_name }}.INSTANCE.toDTO` and `{{ mapper_simple_name }}.INSTANCE.fromDTO`). 
    {% else %}
  * The client/proxy `{{ api_class.client_name }}` should be mapped to/from `{{ api_class.dto_name }}` (defined within the protobuf package `{{ api_class.proto_package }}`) instead of the original class `{{ c_name }}` (which is no longer available). You can use the method toDTO and the static method fromDTO defined in `{{ api_class.client_name }}` to map between the two types. DO NOT import `{{ c_name }}`.
    {% endif %}
  {% endfor %} 
{% endif %}


## Template
##### {{ client_template.name }}.{{ language.extension }}
```{{ language.lowercase }}
{{ client_template.code | safe }}
```
