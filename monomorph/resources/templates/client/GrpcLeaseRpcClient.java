package {{ package_name }}.shared.client;

import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.StatusRuntimeException;
import {{ package_name }}.shared.leasing.LeasingServiceGrpc;
import {{ package_name }}.shared.leasing.*;
import {{ package_name }}.shared.RefactoredObjectID;
import {{ package_name }}.generated.helpers.ServiceRegistry;

import java.util.concurrent.TimeUnit;

/**
 * gRPC implementation of LeaseRpcClient.
 * Connects to the Leasing Service endpoint associated with the RefactoredObjectID's class/service.
 * This assumes that the leasing service is co-located with the object service.
 */
public class GrpcLeaseRpcClient implements LeaseRpcClient {

    private final ManagedChannel channel;
    private final LeasingServiceGrpc.LeasingServiceBlockingStub blockingStub;
    private final RefactoredObjectID instanceId;

    /**
     * Creates a LeaseRpcClient targeting the service responsible for the given object ID.
     * @param objectId The ID of the object whose lease needs management. Used to find the target service endpoint.
     */
    public GrpcLeaseRpcClient(RefactoredObjectID objectId) {
        this.instanceId = objectId;
        ServiceRegistry.ServiceEndpoint endpoint = ServiceRegistry.getEndpoint(objectId.getServiceID());
        this.channel = ManagedChannelBuilder.forAddress(endpoint.getHost(), endpoint.getPort())
                                           .usePlaintext() 
                                           .build();
        this.blockingStub = LeasingServiceGrpc.newBlockingStub(channel);
    }


    @Override
    public boolean acquireLease(String clientId) throws Exception {
        try {
            LeaseRequest request = LeaseRequest.newBuilder()
                    .setInstanceID(instanceId)
                    .setClientID(clientId)
                    .build();
            LeaseResponse response = blockingStub.acquireLease(request);
            return response.getSuccess();
        } catch (StatusRuntimeException e) {
            return false;
        } catch (Exception e) {
            throw e; 
        }
    }

    @Override
    public boolean renewLease(String clientId) throws Exception {
        try {
            LeaseRequest request = LeaseRequest.newBuilder()
                    .setInstanceID(instanceId)
                    .setClientID(clientId)
                    .build();
            LeaseResponse response = blockingStub.renewLease(request);
            return response.getSuccess();
        } catch (StatusRuntimeException e) {
            return false;
        } catch (Exception e) {
            throw e;
        }
    }

    @Override
    public void releaseLease(String clientId) throws Exception {
        try {
            LeaseRequest request = LeaseRequest.newBuilder()
                    .setInstanceID(instanceId)
                    .setClientID(clientId)
                    .build();
            blockingStub.releaseLease(request);
        } catch (StatusRuntimeException e) {
            // Ignore error for best-effort release without logging
        } catch (Exception e) {
            // Ignore error for best-effort release without logging
        }
    }

    @Override
    public void close() throws Exception {
        if (channel != null && !channel.isShutdown()) {
            channel.shutdown().awaitTermination(5, TimeUnit.SECONDS);
            // Force shutdown if needed
             if (!channel.isTerminated()) {
                 channel.shutdownNow();
             }
        }
    }
}