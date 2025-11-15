# Initial instructions
{{ proto_prompt }}

# Developer Response
{{ proto_response }}

# Follow-up instructions
With the proto file created, you will now need to create the server implementation of the gRPC client in {{ language.name }}.
## Instructions
### Implement the client which:
- Must have a stub instance. The host and port values for the stub can be loaded from the environment using the `{{ host_env_var }}` and `{{ port_env_var }}` environment variables.
- Must have an instance ID variable
- It must have constructors with an API identical to the original class. Each constructor creates the stub and calls the createInstance method of the server and records the ID
- It must implement all the methods in the proto files (except the constructors and destructor)
- Must have a finalize method that calls the destructor method of the server
- Must implement the interface `RefactoredObjectClient` and its method toID. 
  - The classID is a static string that can be acquired from the environment through the `{{ class_id_env_var }}` environment variable.
- Must call the toID method whenever one of its inputs implements refactoredObjectClient. The gRPC invocation uses refactoredObjectID instead of the actual client class.
- Can invoke the method fromID from refactoredObjectMapper in order to transform a refactoredObjectID object into its corresponding client class. The class refactoredObjectMapper is already implemented and will be shared below if needed.
- The refactoring must remain seamless for the rest of the classes, which means that instances of the original class will be replaced by instances of the new class (it can have the same name)


{% if client_class is not none %}
## RefactoredObjectClient
##### RefactoredObjectClient.{{ language.extension }}
```{{ language.lowercase }}
{{ client_class.code | safe }}
```
{% endif %}

{% if refactored_object_id_class is not none %}
## refactoredObjectID
##### shared.proto
```protobuf
{{ refactored_object_id_class.code | safe }}
```
{% endif %}

{% if mapper_class is not none %}
## refactoredObjectMapper
##### refactoredObjectMapper.{{ language.extension }}
```{{ language.lowercase }}
{{ mapper_class.code | safe }}
```
{% endif %}
