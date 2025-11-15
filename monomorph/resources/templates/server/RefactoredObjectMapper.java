package {{ package_name }}.shared.server;

import {{ package_name }}.shared.server.LeaseManager;
import {{ package_name }}.shared.RefactoredObjectID;
import {{ package_name }}.generated.helpers.ClassIdRegistry;

import java.util.UUID;


class RefactoredObjectMapper {
    public static RefactoredObjectID mapToRefactoredObjectID(LeaseManager leaseManager, Object newInstance, String className, String serviceId) {
        String classId = ClassIdRegistry.getClassId(className);
        String instanceId = UUID.randomUUID().toString();
        boolean registered = leaseManager.registerInstanceAndGrantLease(
                instanceId,
                classId,
                newInstance,
                serviceId
            );
        if (!registered) {
                throw new RuntimeException("Failed to register new instance ID: " + instanceId);
        }
        return RefactoredObjectID.newBuilder().setInstanceID(instanceId).setClassID(classId).setServiceID(serviceId).build();
    }

    public static Object mapToObject(LeaseManager leaseManager, RefactoredObjectID refactoredObjectID) {
        String instanceId = refactoredObjectID.getInstanceID();
        Object object = leaseManager.getInstance(instanceId);
        if (object == null) {
            throw new RuntimeException("Failed to retrieve instance for ID: " + instanceId);
        }
        return object;
    }
}