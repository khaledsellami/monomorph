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
- Each request message (except for `CreateObjectRequest`) should have a `refactoredObjectID` object as input. 
- `refactoredObjectID` is from the `shared.proto` file as shown in the template. The package name for this file is `{{ shared_proto_package }}`. Do not redefine it.
- If an input or an output is not a primitive type, you can assume that it can be replaced by the imported `refactoredObjectID` object. Make sure to use the fully qualified name of the `{{ shared_proto_package }}.refactoredObjectID` object when referring to it.
- The proto package and service name from the template should be used.


Use your knowledge of {{ language.name }} to think through the changes you will make and explain each step of the process and why you think it is needed. When you are done explaining the reasoning for each change, write the new source code of the proto file in full.

Write your reasoning under the "## Explanation" section and the source code under the "## Result" section. Any additional comments or explanations should be added to a section called "## Comments".
