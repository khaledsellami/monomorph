{# Jinja2 grpc proto prompt template #}
{# Variables:
    language:                       The language to use for the server implementation.
      language.name:                The name of the language.
      language.lowercase:           The lowercase name of the language.
      language.extension:           The file extension of the language. 
    class_:                         The Class object that contains the source code of the class to be refactored.
        class_.name:                The name of the class.
        class_.full_name:           The fully qualified name of the class.
        class_.code:                The code of the class.
    methods:                        The list of methods that are called by external microservices.
    proto_template:                 The template for the protobuf definition.
        server_template.name:       The name of the proto file.
        server_template.code:       The code of the proto template.
    id_only:                        A boolean indicating whether the refactored classes are only represented by their ID.
    shared_proto_package            The package name of the shared proto file that contains the `RefactoredObjectID` message.
    references_mapping:             A dictionary containing information about referenced API classes
        references_mapping.dto:     A dictionary mapping classes that were refactored with the DTO pattern
            c_name:                 The name of the class.
            api_class:              Its metadata class.
                client_name:        The name of the client class.
                dto_name:           The simple name of the DTO class.
                proto_package:      The package name of the DTO class.
                mapper_name:        The fully qualified name of the mapper class.
                proto_filename:     The name of the proto file that contains the DTO class.
        references_mapping.idbased: A dictionary mapping classes that were refactored with the ID pattern (same as above)
#}
You are an excellent enterprise architect and developer who has an extensive background in helping companies rewrite their legacy {{ language.name }} applications to microservices. Your team decided to use protobuf gRPC to communicate between the microservices. Your task is to examine the source code of a local class and then create the classes and files required to enable the RPC. 

The following class `{{ class_.full_name }}` contains the methods [{% for method in methods %}`{{ method }}`, {% endfor %}] which are called by external microservices. 

You need to keep changes to the original classes to a minimum. You will be given the source code of the class in question and the instructions to create the necessary files. 

In order to comply with the existing architecture, you will be given a template of the proto file that you need to fill in. The template will contain the package name, the imports, and the service name.

## Class Source Code
##### {{ class_.name }}.{{ language.extension }}
```{{ language.lowercase }}
{{ class_.code | safe }}
```

## Proto Template
##### {{ proto_template.name }}.proto
```proto
{{ proto_template.code | safe }}
```

## Instructions
### Create a proto file that has the following properties:
- Exposes only the used methods: [{% for method in methods %}`{{ method }}`, {% endfor %}]
- Complies with the createObject rpc in the template which will serve as a wrapper around the constructor. You will need to update the `ConstructorArgs` message to include the arguments for the constructor.
- Has message objects for all inputs and outputs
- Each request message (except for `CreateObjectRequest`) should have a `RefactoredObjectID` object as input. 
- The proto package and service name from the template should be used.
- `RefactoredObjectID` is from the `shared.proto` file as shown in the template. The package name for this file is `{{ shared_proto_package }}`. Do not redefine it.
{% if id_only %}
- If an input or an output is not a primitive type, you can assume that it can be replaced by the imported `RefactoredObjectID` object. Make sure to use the fully qualified name of the `{{ shared_proto_package }}.RefactoredObjectID` object when referring to it. 
{% else %} 
  {% if references_mapping.idbased %}
- The following classes, are represented by the ID message `RefactoredObjectID` (from the proto file `shared.proto`) which should be their replacement in the request and response messages. Make sure to use the fully qualified name of the `{{ shared_proto_package }}.RefactoredObjectID` object when referring to it. Do not redefine the referenced class.
  {% for c_name, c_api_class in references_mapping.idbased.items() %}
  * `{{ c_name }}`.
  {% endfor %} 
{% endif %} 
{% if references_mapping.dto %}
- The following classes are mapped into corresponding DTO classes. If they have to be transferred in a request or response, use the DTO class instead of the original class. Make sure to import their protobuf files and use the fully qualified name of the class when referring to it. Do not redefine the referenced class.
  {% for c_name, c_api_class in references_mapping.dto.items() %}
  * `{{ c_name }}` is mapped into `{{ c_api_class.dto_name }}` (defined within the protobuf package `{{ c_api_class.proto_package }}` and imported from `{{ c_api_class.proto_filename }}`). 
    {% endfor %} 
  {% endif %}
{% endif %}

Use your knowledge of {{ language.name }} to think through the changes you will make and explain each step of the process and why you think it is needed. When you are done explaining the reasoning for each change, write the new source code of the proto file in full.

Write your reasoning under the "## Explanation" section and the source code under the "## Result" section. Any additional comments or explanations should be added to a section called "## Comments".
