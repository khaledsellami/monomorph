{# Jinja2 template for generating a MapStruct mapper interface #}
{# Variables:
    package_name:                   The Java package for the mapper class.
    class_name:                     The simple name of the original domain class.
    dto_name:                       The simple name of the DTO class of the original domain class.
    grpc_service:                   The name of the generated mapper class.
        grpc_service.package_name:  The package name of the gRPC service.
        grpc_service.name:          The simple name of the gRPC service.
    method_names:                   The list of method names to be implemented in the client.
    registry_package_name:          The package name for the ServiceRegistry class.
    target_service_uid:             The unique ID for the target service.
#}
package {{ package_name }}.generated.client;

// gRPC imports
import {{ grpc_service.package_name }}.*;
{% if method_names %}
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import {{ registry_package_name }}.generated.helpers.ServiceRegistry;
{% endif %}

/**
 * Auto-generated DTO gRPC client
 * {@link {{ class_name }}} and {@link {{ dto_name }}}.
 */
public class {{ class_name }} {
    private {{ dto_name }} dtoInstance;

    public {{ class_name }}({{ dto_name }} dtoInstance) {
        // dtoConstructor to initialize from a DTO instance
        this.dtoInstance = dtoInstance;
    }

    // add any additional constructors if needed

    // mapping methods
    public {{ dto_name }} toDTO() {
        return this.dtoInstance;
    }

    public static {{ class_name }} fromDTO({{ dto_name }} dtoInstance) {
        {{ class_name }} instance = new {{ class_name }}(dtoInstance);
        return instance;
    }

    // implementation of the gRPC exposed methods
    {% if method_names %}
    // TARGET_SERVICE_ID is the unique ID for the ClassA service, provided by the tool
    private static final String TARGET_SERVICE_ID = "{{ target_service_uid }}";

    // --- gRPC Specific Fields ---
    private ManagedChannel businessChannel; // Channel for RPC calls
    private {{ grpc_service.name }}Grpc.{{ grpc_service.name }}BlockingStub businessStub; // Use this stub for RPC calls
    
    // Helper methods for gRPC
    protected void performRpcSetup() throws Exception {
        // Use the static TARGET_SERVICE_ID to find the endpoint for business logic calls
        ServiceRegistry.ServiceEndpoint endpoint = ServiceRegistry.getEndpoint(TARGET_SERVICE_ID);
        this.businessChannel = ManagedChannelBuilder.forAddress(endpoint.getHost(), endpoint.getPort()).usePlaintext().build();
        this.businessStub = {{ grpc_service.name }}.newBlockingStub(businessChannel);
    }
    
    protected void performSubclassRpcCleanup() {
        // ... shutdown logic for businessChannel ...
         if (this.businessChannel != null && !this.businessChannel.isShutdown()) {
             try {
                 this.businessChannel.shutdown().awaitTermination(5, TimeUnit.SECONDS);
                  if (!this.businessChannel.isTerminated()) { this.businessChannel.shutdownNow(); }
             } catch (InterruptedException e) {  }
         }
    }
    
    // Implement required methods for gRPC calls here
    // --- START OF gRPC METHOD IMPLEMENTATIONS ---


    // --- END OF gRPC METHOD IMPLEMENTATIONS ---

    {% endif %}

    // Implement all other getters and setters corresponding to the DTO fields
    // --- START OF DTO GETTERS AND SETTERS ---
    // --- END OF DTO GETTERS AND SETTERS ---

}