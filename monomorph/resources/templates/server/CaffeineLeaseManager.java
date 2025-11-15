package {{ package_name }}.shared.server;

// Caffeine imports
import com.github.benmanes.caffeine.cache.CacheLoader;
import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.LoadingCache;
import com.github.benmanes.caffeine.cache.RemovalCause;
import com.github.benmanes.caffeine.cache.RemovalListener;
import com.github.benmanes.caffeine.cache.Scheduler; // Caffeine 2.8.0+

// Java Util imports
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder; // Requires JSR 166 backport or Java 8+ runtime
import java.util.function.BiFunction; // Java 8+ only
import java.util.function.Function; // Java 8+ only

/**
 * Manages object instances and their associated leases using a Caffeine cache for expiration.
 * This class is the central owner of remote object instances within its scope.
 * When the last lease for an object expires or is released, this manager removes its
 * internal reference to the object instance, making it eligible for garbage collection.
 * It does NOT perform any application-specific cleanup on the object itself.
 *
 * Responsibilities:
 *     - Storing actual object instances keyed by a unique instance ID.
 *     - Tracking active leases granted to clients for specific object instances.
 *     - Automatically removing its internal reference to object instances when the last lease expires or is released.
 *
 * This class is designed to be a singleton or shared component within the server application.
 * It requires an external {@link ScheduledExecutorService} for Caffeine's timed operations.
 */
public final class CaffeineLeaseManager implements LeaseManager {

    /** Primary storage for the actual object instances. */
    private final ConcurrentMap<String, Object> managedInstances = new ConcurrentHashMap<String, Object>();

    /** Caffeine cache for tracking active leases and expiry. */
    private final LoadingCache<LeaseKey, String> leaseCache;

    /** Tracks the count of active leases per instance ID. */
    private final ConcurrentMap<String, LongAdder> leaseCounts = new ConcurrentHashMap<String, LongAdder>();

    /** Scheduler required by Caffeine. */
    private final ScheduledExecutorService evictionScheduler;
    /** Lease duration in milliseconds. */
    private final long leaseDurationMillis;

    /**
     * Creates a new CaffeineLeaseManager.
     *
     * @param leaseDurationMillis The duration (in milliseconds) each lease remains valid before expiring if not renewed. Must be positive.
     * @param scheduler           A {@link ScheduledExecutorService} used by Caffeine for managing timed expirations. Must not be null. The caller is responsible for managing its lifecycle.
     * @throws IllegalArgumentException if leaseDurationMillis is not positive.
     * @throws NullPointerException if scheduler is null.
     */
    public CaffeineLeaseManager(
            long leaseDurationMillis,
            ScheduledExecutorService scheduler
    ) {
        if (leaseDurationMillis <= 0) {
            throw new IllegalArgumentException("leaseDurationMillis must be positive");
        }
        this.leaseDurationMillis = leaseDurationMillis;
        this.evictionScheduler = Objects.requireNonNull(scheduler, "scheduler cannot be null");

        // Listener called by Caffeine when a lease entry is removed.
        RemovalListener<LeaseKey, String> removalListener = new RemovalListener<LeaseKey, String>() {
            @Override
            public void onRemoval(LeaseKey key, String instanceId, RemovalCause cause) {
                handleLeaseRemoval(key, instanceId, cause);
            }
        };

        // Configure the Caffeine cache.
        this.leaseCache = Caffeine.newBuilder()
                .expireAfterWrite(this.leaseDurationMillis, TimeUnit.MILLISECONDS)
                .scheduler(Scheduler.forScheduledExecutorService(this.evictionScheduler))
                .removalListener(removalListener)
                .build(new CacheLoader<LeaseKey, String>() {
                     // Dummy loader required by build(). Should not be invoked directly.
                     @Override public String load(LeaseKey key) { return key.getInstanceId(); }
                 });
    }


    @Override
    public boolean registerInstanceAndGrantLease(String instanceId, String classIdIgnored, Object instance, String clientId) {
         Objects.requireNonNull(instanceId, "instanceId cannot be null");
         Objects.requireNonNull(instance, "instance cannot be null");
         Objects.requireNonNull(clientId, "clientId cannot be null");

         Object existing = managedInstances.putIfAbsent(instanceId, instance);
         if (existing != null) { return false; } // ID conflict

         boolean leaseGranted = grantOrRenewLeaseInternal(instanceId, clientId, true);
         if (!leaseGranted) {
             managedInstances.remove(instanceId, instance); // Rollback store
             return false;
         }
         return true;
    }


    @Override
    public Object getInstance(String instanceId) {
         return managedInstances.get(instanceId);
    }


    @Override
    public boolean grantOrRenewLease(String instanceId, String clientId) {
        Objects.requireNonNull(instanceId, "instanceId cannot be null");
        Objects.requireNonNull(clientId, "clientId cannot be null");

        if (!managedInstances.containsKey(instanceId)) { return false; }
        return grantOrRenewLeaseInternal(instanceId, clientId, false);
    }


    @Override
    public void releaseLease(String instanceId, String clientId) {
         Objects.requireNonNull(instanceId, "instanceId cannot be null");
         Objects.requireNonNull(clientId, "clientId cannot be null");
         LeaseKey key = new LeaseKey(instanceId, clientId);
         leaseCache.invalidate(key); // Triggers the removal listener
    }

    /** Internal lease grant/renewal logic. */
    private boolean grantOrRenewLeaseInternal(final String instanceId, final String clientId, boolean isInitialGrant) {
        LeaseKey key = new LeaseKey(instanceId, clientId);
        final LongAdder counter = leaseCounts.computeIfAbsent(instanceId, new Function<String, LongAdder>() {
            @Override public LongAdder apply(String k) { return new LongAdder(); }
        });
        boolean leaseExisted = leaseCache.asMap().containsKey(key);
        leaseCache.put(key, instanceId); // Reset timer
        if (isInitialGrant || !leaseExisted) {
             counter.increment(); // Increment count if new lease or re-grant after expiry
        }
        return true;
    }

    /** Handles lease removal from cache (expiry or explicit release). */
    private void handleLeaseRemoval(LeaseKey key, String instanceId, RemovalCause cause) {
        if (key == null || instanceId == null) return;
        if (cause != RemovalCause.EXPIRED && cause != RemovalCause.EXPLICIT) return;

        LongAdder currentCount = leaseCounts.get(instanceId);
        if (currentCount != null) {
            currentCount.decrement();
            long countAfterDecrement = currentCount.sum();

            if (countAfterDecrement <= 0) {
                 boolean removedCounter = leaseCounts.computeIfPresent(instanceId, new BiFunction<String, LongAdder, LongAdder>() {
                     @Override public LongAdder apply(String id, LongAdder adder) { return adder.sum() <= 0 ? null : adder; }
                 }) == null;

                if (removedCounter) {
                    // *** SIMPLIFIED DESTRUCTION ***
                    // Last lease gone, simply remove the reference from the map.
                    // GC will reclaim the object if this was the last strong reference.
                    managedInstances.remove(instanceId);
                }
            }
        }
    }


    @Override
    public void shutdown() {
        // Shutdown scheduler
        if (evictionScheduler != null && !evictionScheduler.isShutdown()) {
             evictionScheduler.shutdown();
             try {
                 if (!evictionScheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                     evictionScheduler.shutdownNow();
                 }
             } catch (InterruptedException e) {
                 evictionScheduler.shutdownNow();
                 Thread.currentThread().interrupt();
             }
        }
        // Clean up cache (discard entries without triggering listeners heavily)
        leaseCache.cleanUp();
        // Clear internal state
        managedInstances.clear();
        leaseCounts.clear();
    }

    /**
     * Finds the unique instance ID associated with a given object instance reference.
     * This performs a reverse lookup based on the exact object reference stored by the manager.
     * This operation iterates through the managed instances and may be slow on large sets.
     *
     * @param instance The exact object instance reference to look up. Must not be null.
     * @return The instance ID associated with the provided object instance, or {@code null} if the
     *         exact instance reference is not currently managed by this LeaseManager.
     * @throws NullPointerException if the provided {@code instance} is null.
     */
    @Override
    public String findInstanceIdForInstance(Object instance) {
        Objects.requireNonNull(instance, "instance cannot be null");
        // Iterate through the map entries to find a matching *value* reference.
        for (Map.Entry<String, Object> entry : managedInstances.entrySet()) {
            // Use reference equality (==) because we need the exact same object instance.
            if (entry.getValue() == instance) {
                return entry.getKey(); // Return the associated instance ID (key)
            }
        }
        return null; // Instance not found in the map
    }
}