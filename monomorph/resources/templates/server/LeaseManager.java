package {{ package_name }}.shared.server;


/**
 * Interface defining the contract for managing remote object instances and their associated leases.
 * Implementations handle the storage of instances, tracking of client leases, and automatic
 * cleanup based on lease expiry or explicit release.
 */
public interface LeaseManager {

    /**
     * Registers a newly created object instance with the manager, stores it,
     * and grants the initial lease to the requesting client.
     * Implementations must handle storage of the {@code instance} object, associate it
     * with the unique {@code instanceId}, track the lease for the {@code clientId},
     * and potentially handle ID conflicts.
     *
     * @param instanceId The unique ID generated for the new object instance. Must not be null.
     * @param classId    The identifier for the type of the object (e.g., "ClassA"). May be used for type-specific logic like cleanup if implemented. Must not be null or empty if used by implementation.
     * @param instance   The actual object instance to be managed. Must not be null.
     * @param clientId   The unique identifier of the client receiving the initial lease. Must not be null.
     * @return {@code true} if the instance was successfully registered and the initial lease granted;
     *         {@code false} if registration failed (e.g., an instance with the same {@code instanceId} already exists).
     * @throws NullPointerException if instanceId, instance, or clientId is null (implementations should check).
     * @throws Exception for other potential internal errors during registration or lease grant.
     */
    boolean registerInstanceAndGrantLease(String instanceId, String classId, Object instance, String clientId) throws Exception;

    /**
     * Retrieves a managed object instance by its unique ID.
     * This provides access to the object but does not guarantee that the calling client holds a valid lease.
     * It confirms the object is currently managed and has not been cleaned up.
     *
     * @param instanceId The unique ID of the object instance to retrieve.
     * @return The object instance, or {@code null} if no instance with that ID is currently managed.
     * @throws Exception for potential internal errors during retrieval.
     */
    Object getInstance(String instanceId) throws Exception;

    /**
     * Grants a lease to a client for an *existing* object instance, or renews an existing lease.
     * <p>
     * The object instance identified by {@code instanceId} must already be managed by this LeaseManager.
     *
     * @param instanceId The unique ID of the existing object instance. Must not be null.
     * @param clientId   The unique identifier of the client acquiring or renewing the lease. Must not be null.
     * @return {@code true} if the lease was successfully granted or renewed;
     *         {@code false} if the object instance specified by {@code instanceId} does not exist or lease could not be granted/renewed.
     * @throws NullPointerException if instanceId or clientId is null (implementations should check).
     * @throws Exception for other potential internal errors during lease grant/renewal.
     */
    boolean grantOrRenewLease(String instanceId, String clientId) throws Exception;

    /**
     * Explicitly releases a lease held by a specific client for a specific object instance.
     * <p>
     * Triggering this usually accelerates the potential cleanup of the object if this was the last lease.
     * Implementations should handle this as a best-effort operation where possible.
     *
     * @param instanceId The unique ID of the object instance whose lease is being released. Must not be null.
     * @param clientId   The unique identifier of the client releasing the lease. Must not be null.
     * @throws NullPointerException if instanceId or clientId is null (implementations should check).
     * @throws Exception for potential internal errors during lease release (though often suppressed for best-effort).
     */
    void releaseLease(String instanceId, String clientId) throws Exception;

    /**
     * Shuts down the lease manager, performing any necessary cleanup of internal resources
     * (e.g., caches, background threads, connections).
     * May optionally attempt cleanup of remaining managed object instances depending on implementation strategy.
     */
    void shutdown();

    /**
     * Finds the unique instance ID associated with a given object instance reference.
     * This performs a reverse lookup based on the exact object reference stored by the manager.
     *
     * @param instance The exact object instance reference to look up. Must not be null.
     * @return The instance ID associated with the provided object instance, or {@code null} if the
     *         exact instance reference is not currently managed by this LeaseManager.
     * @throws NullPointerException if the provided {@code instance} is null.
     */
    String findInstanceIdForInstance(Object instance);
}