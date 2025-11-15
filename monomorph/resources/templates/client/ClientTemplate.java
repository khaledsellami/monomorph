{# Jinja2 template for a gRPC service implementation #}
{# Variables:
    package_name:                   The base package for the service class.
    grpc_service:                   Details about the gRPC service being implemented.
        grpc_service.name:          The name of the gRPC service.
        grpc_service.package_name:  The package name of the gRPC service.
    class_name:                     The name of the client/proxy class.
    target_service_uid:             The unique ID for the target service.
#}
package {{ package_name }}.generated.client;

import {{ package_name }}.shared.client.AbstractRefactoredClient;
import {{ package_name }}.generated.helpers.ServiceRegistry;
import {{ package_name }}.shared.RefactoredObjectID; 
// gRPC imports
import {{ grpc_service.package_name }}.*;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
// Add messages and stubs as needed

import java.util.concurrent.TimeUnit;


// Class template. Add the necessary methods and fields
public class {{ class_name }} extends AbstractRefactoredClient {

    // TARGET_SERVICE_ID is the unique ID for the ClassA service, provided by the tool
    private static final String TARGET_SERVICE_ID = "{{ target_service_uid }}";

    // --- gRPC Specific Fields ---
    private ManagedChannel businessChannel; // Channel for RPC calls
    private {{ grpc_service.name }}Grpc.{{ grpc_service.name }}BlockingStub businessStub; // Use this stub for RPC calls

    /** constructor. */
    public {{ class_name }}(ReplaceWithActualArgs replaceWithActualArgs) { // remove replaceWithActualArgs if there are no constructor args
        // MAKE SURE TO CALL THIS INITIALIZATION METHOD FROM THE PARENT (void initialize(Object... args))
        // Include other constructor args as needed
        initialize(replaceWithActualArgs);
    }

     /** Private constructor used by the fromID factory. */
     private {{ class_name }}(RefactoredObjectID existingId) {
         super(existingId); // Use the base constructor for existing IDs
     }

    // --- Implementation of Abstract Methods ---

    @Override
    protected void performRpcSetup() throws Exception {
        // Use the static TARGET_SERVICE_ID to find the endpoint for business logic calls
        ServiceRegistry.ServiceEndpoint endpoint = ServiceRegistry.getEndpoint(TARGET_SERVICE_ID);
        this.businessChannel = ManagedChannelBuilder.forAddress(endpoint.getHost(), endpoint.getPort()).usePlaintext().build();
        this.businessStub = {{ grpc_service.name }}.newBlockingStub(businessChannel);
    }

    @Override
    protected RefactoredObjectID performRemoteCreateAndGetId(String clientId, Object... args) throws Exception {
        performRpcSetup();
        // Start of logic for creating the RPC "createObject" request
        // Use the args to create the request object with proper type mapping
        // Make sure to add clientId to the request
        // End of logic for creating the RPC "createObject" request
                
        RefactoredObjectID createResponseProto = this.businessStub.createObject(createRequest);

        return createResponseProto;
    }

    @Override
    protected void performSubclassRpcCleanup() {
        // ... shutdown logic for businessChannel ...
         if (this.businessChannel != null && !this.businessChannel.isShutdown()) {
             try {
                 this.businessChannel.shutdown().awaitTermination(5, TimeUnit.SECONDS);
                  if (!this.businessChannel.isTerminated()) { this.businessChannel.shutdownNow(); }
             } catch (InterruptedException e) {  }
         }
    }

    /** Factory method for creating proxy from an EXISTING ID. */
    @Override
     public static {{ class_name }} fromID(RefactoredObjectID existingId) {
         return new {{ class_name }}(existingId);
     }

    // --- Start of the implementation of the rest of the Service Methods ---
    // Add the rest of the service methods here
    
    // --- End of the implementation of the rest of the Service Methods ---

} 