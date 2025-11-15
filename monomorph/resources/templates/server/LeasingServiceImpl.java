package {{ package_name }}.shared.server;

// gRPC imports
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.stub.StreamObserver;

// Generated Proto imports
import {{ package_name }}.shared.leasing.LeasingServiceGrpc;
import {{ package_name }}.shared.leasing.LeaseRequest;
import {{ package_name }}.shared.leasing.LeaseResponse;
import {{ package_name }}.shared.RefactoredObjectID;

// Java Util imports
import java.util.Objects;

/**
 * Implements the gRPC {@code LeasingService}.
 * Delegates the actual leasing logic to a {@link LeaseManager} implementation.
 */
public class LeasingServiceImpl extends LeasingServiceGrpc.LeasingServiceImplBase {

    /** The backend lease manager (interface type). */
    private final LeaseManager leaseManager;

    /**
     * Creates a new LeasingServiceImpl.
     *
     * @param leaseManager The configured {@link LeaseManager} instance. Must not be null.
     */
    public LeasingServiceImpl(LeaseManager leaseManager) { // Depend on interface
        this.leaseManager = Objects.requireNonNull(leaseManager, "leaseManager cannot be null");
    }

    @Override
    public void acquireLease(LeaseRequest request, StreamObserver<LeaseResponse> responseObserver) {
        boolean success = false;
        try {
            RefactoredObjectID objectIdProto = request.getInstanceID();
            String clientId = validateAndGetClientID(request);
            String instanceId = objectIdProto.getInstanceID();

            // Delegate to the LeaseManager interface method
            success = leaseManager.grantOrRenewLease(instanceId, clientId);

            LeaseResponse response = LeaseResponse.newBuilder().setSuccess(success).build();
            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (IllegalArgumentException e) {
            responseObserver.onError(Status.INVALID_ARGUMENT.withDescription(e.getMessage()).asRuntimeException());
        } catch (Exception e) { // Catch broader exceptions from interface methods
            responseObserver.onError(Status.INTERNAL.withDescription("Failed to process acquireLease request: " + e.getMessage()).withCause(e).asRuntimeException());
        }
    }

    @Override
    public void renewLease(LeaseRequest request, StreamObserver<LeaseResponse> responseObserver) {
         boolean success = false;
        try {
            RefactoredObjectID objectIdProto = request.getInstanceID();
            String clientId = validateAndGetClientID(request);
            String instanceId = objectIdProto.getInstanceID();

            // Delegate to the LeaseManager interface method
            success = leaseManager.grantOrRenewLease(instanceId, clientId);

            LeaseResponse response = LeaseResponse.newBuilder().setSuccess(success).build();
            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (IllegalArgumentException e) {
             responseObserver.onError(Status.INVALID_ARGUMENT.withDescription(e.getMessage()).asRuntimeException());
        } catch (Exception e) {
             responseObserver.onError(Status.INTERNAL.withDescription("Failed to process renewLease request: " + e.getMessage()).withCause(e).asRuntimeException());
        }
    }

    @Override
    public void releaseLease(LeaseRequest request, StreamObserver<LeaseResponse> responseObserver) {
         boolean callCompletedWithoutError = true;
         try {
             RefactoredObjectID objectIdProto = request.getInstanceID();
             String clientId = validateAndGetClientID(request);
             String instanceId = objectIdProto.getInstanceID();

             // Delegate to the LeaseManager interface method
             leaseManager.releaseLease(instanceId, clientId);

             // Respond success if no exception occurred
             LeaseResponse response = LeaseResponse.newBuilder().setSuccess(callCompletedWithoutError).build();
             responseObserver.onNext(response);
             responseObserver.onCompleted();
         } catch (IllegalArgumentException e) {
              responseObserver.onError(Status.INVALID_ARGUMENT.withDescription(e.getMessage()).asRuntimeException());
         } catch (Exception e) {
              // Indicate internal failure during release attempt
              responseObserver.onError(Status.INTERNAL.withDescription("Failed to process releaseLease request: " + e.getMessage()).withCause(e).asRuntimeException());
         }
    }

    /**
     * Validates the client ID from the request and returns it.
     *
     * @param request The LeaseRequest containing the client ID.
     * @return The validated client ID.
     * @throws IllegalArgumentException if the client ID is invalid.
     */
    private String validateAndGetClientID(LeaseRequest request) {
        String clientId = request.getClientID();
        if (clientId == null || clientId.isEmpty()) {
            throw new IllegalArgumentException("Client ID cannot be null or empty");
        }
        return clientId;
    }
}