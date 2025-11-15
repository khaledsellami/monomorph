You are an excellent enterprise architect and developer who has an extensive background in helping companies rewrite their legacy {{ language.name }} applications to microservices. Your team decided to use protobuf gRPC to communicate between the microservices. Your task is to examine the source code of a local class and then create the classes and files required to enable the RPC. 

The following class `{{ class_.full_name }}` contains the methods [{% for method in methods %}`{{ method }}`, {% endfor %}] which are called by external microservices. 

You need to keep changes to the original classes to a minimum. You will be given the source code of the class in question and the instructions to create the necessary files. 

In order to comply with the existing architecture, you will be given a template of the proto file that you need to fill in. The template will contain the package name and the service name.

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
- Creates a message that represents the Data Transfer Object (DTO) for the class `{{ class_.name }}`. The message should be named `{{ class_.name }}DTO` and should contain at least the following fields from the class: 
{% for field in fields %}`{{ field }}`,  {% endfor %} and any other fields that are necessary to represent the class.
- The fields must retain the same names as in the original source code even if they do not follow the protobuf naming conventions.
{% if methods %}
- Exposes only the used methods: [{% for method in methods %}`{{ method }}`, {% endfor %}]
- Has message objects for all inputs and outputs
- Each request and response message should include the `{{ class_.name }}DTO` message in addition to the other fields (corresponding to the inputs or outputs).
{% endif %}
- The proto package and service name from the template should be used.
{% if references_mapping.idbased %}
- The following classes, are represented by the ID message `refactoredObjectID` which should be their replacement in the request and response messages. Make sure to use the fully qualified name of the `{{ shared_proto_package }}.refactoredObjectID` object when referring to it.
  {% for c_name, c_api_class in references_mapping.idbased.items() %}
  * `{{ c_name }}`.
  {% endfor %} 
{% endif %} 
{% if references_mapping.dto %}
- The following classes are mapped into corresponding DTO classes. If they have to be transferred in a request or response, use the DTO class instead of the original class. Make sure to import their protobuf files and use the fully qualified name of the class when referring to it.
  {% for c_name, c_api_class in references_mapping.dto.items() %}
  * `{{ c_name }}` is mapped into `{{ c_api_class.dto_name }}` (defined within the protobuf package `{{ c_api_class.proto_package }}` and imported from `{{ c_api_class.proto_filename }}`). 
  {% endfor %} 
{% endif %}


Use your knowledge of {{ language.name }} to think through the changes you will make and explain each step of the process and why you think it is needed. When you are done explaining the reasoning for each change, write the new source code of the proto file in full.

Write your reasoning under the "## Explanation" section and the source code under the "## Result" section. Any additional comments or explanations should be added to a section called "## Comments".
