{# Jinja2 template for a gRPC service implementation #}
{# Variables:
    package_name:                   The base package for the service class.
    grpc_service:                   Details about the gRPC service being implemented.
        grpc_service.impl_name:     The name of this gRPC service implementation class.
        grpc_service.name:          The name of the gRPC service.
        grpc_service.package_name:  The package name of the gRPC service.
    original_class:                 Details about the original class being refactored. (name, full_name)
        original_class.name:        The name of the original class.
        original_class.full_name:         The fully qualified name of the original class.
#}
package {{ package_name }}.generated.server;

import io.grpc.stub.StreamObserver;
import {{ grpc_service.package_name }}.*;
// Import other necessary gRPC classes
import {{ package_name }}.shared.server.LeaseManager;
import {{ package_name }}.shared.server.ServerObjectManager;
import {{ package_name }}.shared.RefactoredObjectID;
import {{ package_name }}.generated.helpers.ServiceRegistry;
import {{ package_name }}.generated.helpers.ClassIdRegistry;
import {{ original_class.full_name }}; // The actual business class
// rest of arg imports added here

import java.util.Objects;
import java.util.UUID;

/**
 * gRPC Service implementation for {{ original_class.name }}.
 * - Handles gRPC requests for {{ original_class.name }} API.
 * - Creates transient {{ original_class.name }} instances.
 * - Interacts with LeaseManager for instance registration/retrieval.
 * - Calls business methods on retrieved {{ original_class.name }} instances.
 */
public class {{ grpc_service.impl_name }} extends {{ grpc_service.name }}Grpc.{{ grpc_service.name }}ImplBase  implements ServerObjectManager {

    private final LeaseManager leaseManager;
    private final String serviceId = ServiceRegistry.getServiceId();

    // Static identifier for the class type managed by this service
    public static final String CLASS_ID = ClassIdRegistry.getClassId("{{ original_class.name }}");

    public {{ grpc_service.impl_name }}(LeaseManager leaseManager) {
        this.leaseManager = Objects.requireNonNull(leaseManager);
        this.serviceId = Objects.requireNonNull(serviceId);
    }

    // --- createObject gRPC Method Implementation ---

    @Override
    public void createObject(CreateObjectRequest request, StreamObserver<RefactoredObjectID> responseObserver) {
        try {
            // 1. Extract args & client ID
            String clientId = request.getClientID();
            ConstructorArgs someArgs = request.getConstructorArgs();
            // --- Start of generated code ---
            // Map proto to actual args (if needed)
            // Add logic to map proto to args here
            // --- End of generated code ---

            // 2. *** Create the transient instance DIRECTLY ***
            // --- Start of generated code ---
            // Add the proper logic to create or retrieve the instance
            ClassA newInstance = // logic to create newInstance. This is a placeholder and should be replaced with the actual constructor call
            // --- End of generated code ---

            // 3- Generate a RefactoredObjectID ID
            RefactoredObjectID responseProto = toID(newInstance, clientId);
            // 4. Send the response
            responseObserver.onNext(responseProto);
            responseObserver.onCompleted();
        } catch (Exception e) {
            responseObserver.onError("e");
        }
    }

    // --- Start of ServerObjectManager method implementations ---
    @Override
    public RefactoredObjectID toID(Object instance, String clientId) throws Exception {
            // Validate if id instance exists
            String instanceId = leaseManager.findInstanceIdForInstance(instance);
            if (instanceId == null) {
                // Generate a new unique instance ID
                instanceId = UUID.randomUUID().toString();
            }
            // Register with LeaseManager
            boolean registered = leaseManager.registerInstanceAndGrantLease(instanceId, CLASS_ID, instance, clientId);
            if (!registered) {
                 throw new RuntimeException("Failed to register new instance ID: " + instanceId);
            }
            // Build RefactoredObjectID
            RefactoredObjectID responseProto = RefactoredObjectID.newBuilder().setInstanceID(instanceId).setClassID(CLASS_ID).setServiceID(this.serviceId).build();
            return responseProto;
    }

    @Override
    public RefactoredObjectID toID(Object instance) throws Exception {
        toID(instance, serviceId);
    }

    @Override
    public {{ original_class.name }} fromID(RefactoredObjectID id) throws Exception {
        // Validate the class ID
        if (id.getClassID == null || !id.getClassID().equals(CLASS_ID)) {
            throw new IllegalArgumentException("class ID mismatch: expected " + CLASS_ID + ", got " + id.getClassID());
        }
        // Retrieve the instance from LeaseManager
        // Note: The LeaseManager.getInstance() method should return the correct type based on the class ID
        {{ original_class.name }} instance = ({{ original_class.name }}) leaseManager.getInstance(id.getInstanceID());
        if (instance == null) {
            throw new IllegalArgumentException("No instance found for ID: " + id);
        }
        return instance;
    }

    @Override
    String getManagedClassId() {
        return CLASS_ID;
    }

    @Override
    String getServiceId() {
        return serviceId;
    }
    // --- End of ServerObjectManager method implementations ---

    // --- Other gRPC methods defined in the proto file ---
    // --- Start of generated code ---
    // Add other gRPC method implementations here
    // For example:
    // ---- Start of example method implementation ----
    // @Override
    // public void someOtherMethod(SomeRequest request, StreamObserver<SomeResponse> responseObserver) {
    //     // Retrieve the instance id from the request
    //     RefactoredObjectID instanceId = request.getInstanceID();
    //     // Use the leaseManager to get the instance
    //     {{ original_class.name }} instance = ({{ original_class.name }}) leaseManager.getInstance(instanceId.getInstanceID());
    //     // rest if mapping and business logic
    //     // Build and send the response
    // }
    // ---- End of example method implementation ----
    // --- End of generated code ---

}