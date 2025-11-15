{# Jinja2 grpc server prompt template #}
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
#}
# Initial instructions
{{ proto_prompt }}

# Developer Response
{{ proto_response }}

# Follow-up instructions
With the proto file created, you will now need to create the client implementation of the gRPC client in {{ language.name }}. You can use the given template as a basis.
## Instructions
### Implement the client which:
- Must have constructors with an API identical to the original class. A blueprint of the constructor implementation is provided in the template. Make sure to change it to match the original class arguments and to add any additional constructors if needed.
- Must keep the special private constructor that takes as input a RefactoredObjectID object. 
- Must implement all the methods in the proto files (except `createObject` which must be called in the `performRemoteCreateAndGetId` method).
- Must have a stub instance. The host and port values for the stub are loaded from the `ServiceRegistry` class using the value of `TARGET_SERVICE_ID` as a key. This step is already implemented in the template in the method `performRpcSetup`.
- Each client is associated with an ID that is used to identify the instance. This is already handled by the `AbstractRefactoredClient` parent class.
- The client class inherits the following fields from its parent class `AbstractRefactoredClient`:
  - `protected final String clientId;`
  - `protected final RefactoredObjectID objectId;`
- The refactoring must remain seamless for the rest of the classes. It means that all classes that interact with instances of the original class `{{ client_template.name }}` should not be aware of the refactoring and will call the new client class `{{ client_template.name }}` as if it were the original class.
- The package name and the class name of the new client class should be retained from the template.
- Some methods in the template are incomplete. Make sure to implement their proper logic.
{% if mapper_class is not none %}
- If an argument or return type in the original methods corresponds to `RefactoredObjectID` in the proto file, the client must map between the two types. For this reason we provide the `{{ mapper_class.full_name }}` utility class. It exposes the static methods `fromID` and `toID` to convert between the two types. Its api is:
  - `public static Object fromID(RefactoredObjectID id)`: Converts a `RefactoredObjectID` to the original or proxy class instance.
  - `public static RefactoredObjectID toID(Object object)`: Converts an original or proxy class instance to a `RefactoredObjectID`.
{% endif %}


{% if id_class is not none %}
## RefactoredObjectID
##### shared.proto
```proto
{{ id_class.code | safe }}
```
{% endif %}

## Template
##### {{ client_template.name }}.{{ language.extension }}
```{{ language.lowercase }}
{{ client_template.code | safe }}
```
