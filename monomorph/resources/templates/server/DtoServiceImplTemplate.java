{# Jinja2 template for a gRPC service implementation #}
{# Variables:
    package_name:                   The base package for the service class.
    grpc_service:                   Details about the gRPC service being implemented.
        grpc_service.impl_name:     The name of this gRPC service implementation class.
        grpc_service.name:          The name of the gRPC service.
        grpc_service.package_name:  The package name of the gRPC service.
    original_class:                 Details about the original class being refactored. (name, full_name)
        original_class.name:        The name of the original class.
        original_class.full_name:   The fully qualified name of the original class.
    dto_name:                       The simple name of the DTO class.
    mapper_class:                   The mapper class that translates between DTO and domain objects.
        mapper_class.name:          The name of the mapper class.
        mapper_class.full_name:     The fully qualified name of the mapper class.
#}
package {{ package_name }}.generated.server;

import io.grpc.stub.StreamObserver;
import {{ grpc_service.package_name }}.*;
// Import other necessary gRPC classes

import {{ original_class.full_name }}; // The actual business/domain class
import {{ mapper_class.full_name }};
// rest of arg imports added here

/**
 * gRPC Service implementation for {{ original_class.name }}.
 * - Handles gRPC requests for {{ original_class.name }} API.
 * - Interacts with Mapper for switching between DTO and {{ original_class.name }} instances.
 */
public class {{ grpc_service.impl_name }} extends {{ grpc_service.name }}Grpc.{{ grpc_service.name }}ImplBase {

    // --- Other gRPC methods defined in the proto file ---
    // --- Start of generated code ---
    // Add other gRPC method implementations here
    // For example:
    // ---- Start of example method implementation ----
    // @Override
    // public void someOtherMethod(SomeRequest request, StreamObserver<SomeResponse> responseObserver) {
    //     // Retrieve the DTO from the request
    //     {{ dto_name }} dto = request.getDto();
    //     // Map the DTO to the original class
    //     {{ original_class.name }} original = {{ mapper_class.name }}.INSTANCE.fromDTO(dto);
    //     // Call the corresponding business logic method
    //     ExampleOutput output = original.someOtherMethod(restOfArgsFromRequest);
    //     // Map the output back to the DTO (only if someOtherMethod potentially modifies the original)
    //     {{ dto_name }} responseDto = {{ mapper_class.name }}.INSTANCE.toDTO(original);
    //     // Build and send the response
    // }
    // ---- End of example method implementation ----
    // --- End of generated code ---

}