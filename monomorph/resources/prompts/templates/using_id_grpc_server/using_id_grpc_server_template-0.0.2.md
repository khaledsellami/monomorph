# Initial instructions
{{ proto_prompt }}

# Developer Response
{{ proto_response }}

# Follow-up instructions
With the proto file created, you will now need to create the server implementation of the gRPC service in {{ language.name }}.
## Instructions
### Implement the server which:
- Has a container that maps IDs to the original class instances
- Has a retrieve instance by ID method
- Implements each service in the proto file
- Each non-static and non-constructor method starts by retrieving the instance using the ID (if it was provided) and then calls the actual method (from the original class)
- The constructor creates a new instance (or retrieves the singleton if it's the case), generates an ID, saves the ID and instance couple in the map and returns the ID:
  - If the original class is a singleton, the constructor should return the same ID for each call.
  - The classID is a constant that can be acquired from the environment through the `{{ class_id_env_var }}` environment variable.
  - the ID is generated with UUID-like approach.
- The destructor attempts to remove the instance from the map if it exists based on the ID
- Does not expose the server yet since that will be done in the main function later
- if there's a refactoredObjectID in the protobuf file (that does not correspond to the original class), The server class must invoke the method fromID from refactoredObjectMapper in order to transform a refactoredObjectID object into its corresponding client class. The class refactoredObjectMapper is already implemented and will be shared below if needed.

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
