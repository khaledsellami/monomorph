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
- The constructor creates a new instance, generates an ID, saves the ID and instance couple in the map and returns the ID.
- The destructor attempts to remove the instance from the map if it exists based on the ID
- Does not expose the server yet since that will be done in the main function later
- if there's a refactoredObjectID in the protobuf file, The server class must invoke the method fromID from refactoredObjectMapper in order to transform a refactoredObjectID object into its corresponding client class. The class refactoredObjectMapper is already implemented and will be shared below if needed.

{% if mapper_class is not none %}
## refactoredObjectMapper
##### refactoredObjectMapper.{{ language.extension }}
```{{ language.lowercase }}
{{ mapper_class.code | safe }}
```
{% endif %}
