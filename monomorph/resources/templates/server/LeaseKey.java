package {{ package_name }}.shared.server;

import java.io.Serializable;
import java.util.Objects; 

/**
 * Uniquely identifies a specific lease held by a client for a specific object instance.
 * Used as the key in the Caffeine cache. Immutable.
 */
public final class LeaseKey implements Serializable {
    private static final long serialVersionUID = 1L; 

    private final String instanceId;
    private final String clientId;

    /**
     * Creates a new LeaseKey.
     *
     * @param instanceId The unique ID of the object instance. Must not be null.
     * @param clientId   The unique ID of the client holding the lease. Must not be null.
     * @throws NullPointerException if instanceId or clientId is null.
     */
    public LeaseKey(String instanceId, String clientId) {
        // Using Objects.requireNonNull is generally acceptable for Java 7+ builds
        // If strictly targeting only Java 7 *runtime features*, use a manual check.
        this.instanceId = Objects.requireNonNull(instanceId, "instanceId cannot be null in LeaseKey");
        this.clientId = Objects.requireNonNull(clientId, "clientId cannot be null in LeaseKey");
    }

    public String getInstanceId() {
        return instanceId;
    }

    public String getClientId() {
        return clientId;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        LeaseKey leaseKey = (LeaseKey) o;
        // Both fields must match for equality.
        if (!instanceId.equals(leaseKey.instanceId)) return false;
        return clientId.equals(leaseKey.clientId);
    }

    @Override
    public int hashCode() {
        int result = instanceId.hashCode();
        result = 31 * result + clientId.hashCode();
        return result;
    }

    @Override
    public String toString() {
        return "LeaseKey{" +
               "instanceId='" + instanceId + '\'' +
               ", clientId='" + clientId + '\'' +
               '}';
    }
}