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
# Initial instructions
{{ proto_prompt }}

# Developer Response
{{ proto_response }}

# Follow-up instructions
With the proto file created, you will now need to create the server implementation of the gRPC service in {{ language.name }} using the given template as a basis.
## Instructions
### Implement the server which:
- Implements each service in the proto file. 
- Each non-static and non-constructor method starts by retrieving the instance using the ID and then calls the actual method (from the original class) like the example in the template.
- The constructor (called `createObject`) creates a new instance (or retrieves the singleton if it's the case), generates an ID, registers the ID and instance couple with the lease manager and returns a `RefactoredObjectID` instance based on the ID, the classID and the serviceID.
  - The classID is a static string that can be acquired from the `{{ class_id_registry_full_name }}` utility class.
  - the instanceID is generated with UUID-like approach.
  - If the original class is a singleton, the constructor should look for the singleton instance and return the same instanceID for each call. Implement this logic only if the original class is a singleton.
  - The implementation of the rpc `createObject` in the template is incomplete. The arg mapping logic should be added to the method.
- Does not expose the server yet since that will be done in the main function later.
- The package name and the class name of the server class defined in the template should be used.
{# Class mapping section #}
{% if references_mapping.idbased or id_only %}
- Some method input and output types have been changed to `RefactoredObjectID` in the proto file.  
  - The types can be a class from the original code or a proxy/client of the class.
  - Each proxy/client will have the same name as the class it represents. 
  - Mapping between `RefactoredObjectID` and the original/proxy class instance should be done using the `{{ mapper_class.full_name }}` utility class. It exposes the static methods `fromID` and `toID` to convert between the two types. Its api is:
    - `public static Object fromID(RefactoredObjectID id)`: Converts a `RefactoredObjectID` to the original or proxy class instance. Make sure to cast the result to the correct type.
    - `public static RefactoredObjectID toID(Object object)`: Converts an original or proxy class instance to a `RefactoredObjectID`.
  {% if not id_only %}
  - The relevant classes are: 
    {% for c_name, api_class in references_mapping.idbased.items() %}
      {% if api_class.microservice == current_microservice %}
    * `{{ c_name }}` should be mapped to/from  `RefactoredObjectID`
      {% else %}
    * The client/proxy `{{ api_class.client_name }}` should be mapped to/from `RefactoredObjectID` instead of the original class `{{ c_name }}` (which is no longer available). DO NOT import `{{ c_name }}`.
      {% endif %}
    {% endfor %} 
  {% endif %}
{% endif %}
{% if references_mapping.dto and not id_only %}
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


{% if id_class is not none %}
## RefactoredObjectID
##### shared.proto
```proto
{{ id_class.code | safe }}
```
{% endif %}

## Template
##### {{ server_template.name }}.{{ language.extension }}
```{{ language.lowercase }}
{{ server_template.code | safe }}
```
