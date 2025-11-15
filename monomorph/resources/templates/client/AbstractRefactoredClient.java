package {{ package_name }}.shared.client;

import {{ package_name }}.shared.RefactoredObjectID;
import {{ package_name }}.generated.helpers.ServiceRegistry;

import java.lang.ref.PhantomReference;
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public abstract class AbstractRefactoredClient implements AutoCloseable {

    // --- Static Shared Resources ---
    private static final ScheduledExecutorService sharedScheduler = createSharedScheduler();
    private static final long leaseRenewalFrequencyMillis = loadRenewalFrequency();

    // Java 8 compatible cleanup mechanism
    private static final ReferenceQueue<AbstractRefactoredClient> referenceQueue = new ReferenceQueue<>();
    private static final ConcurrentHashMap<PhantomReference<AbstractRefactoredClient>, CleanupState> cleanupMap = new ConcurrentHashMap<>();
    private static final Thread cleanupThread = createCleanupThread();

    // --- Instance Specific Fields ---
    protected final String clientId = ServiceRegistry.getThisServiceId();
    protected RefactoredObjectID objectId;
    private LeaseRpcClient instanceLeaseRpcClient;

    private final AtomicBoolean leasingActive = new AtomicBoolean(false);
    private final AtomicBoolean closed = new AtomicBoolean(false);

    // State needed for cleanup, managed by the PhantomReference mechanism
    private CleanupState cleanupState; // Holds LeaseRpcClient, clientId, renewalFuture
    private PhantomReference<AbstractRefactoredClient> phantomReference; // Handle to the registered cleanup action

    protected void initialize(Object... args) {
        RefactoredObjectID obtainedObjectId = null;
        try {
            // Perform remote creation and get the object ID (done in the subclass)
            obtainedObjectId = performRemoteCreateAndGetId(clientId, args);
            checkNotNull(obtainedObjectId, "performRemoteCreateAndGetId cannot return null");
            this.objectId = obtainedObjectId;
            // Initialize the LeaseRpcClient (a gRPC client for now)
            this.instanceLeaseRpcClient = createLeaseRpcClient(this.objectId);
            checkNotNull(this.instanceLeaseRpcClient, "LeaseRpcClient cannot be null");

            leasingActive.set(true); // Mark as active now
            // Schedule renewals and register with PhantomReference
            ScheduledFuture<?> renewalFuture = scheduleLeaseRenewalTask(this.objectId);
            setupPhantomReference(renewalFuture);
        } catch (Exception e) {
            cleanupAfterInitFailure();
            throw new InitializationException("Failed to initialize refactored client proxy: " + e.getMessage(), e);
        }
    }

    // Constructor for existing IDs
    protected AbstractRefactoredClient(RefactoredObjectID existingObjectId) {
        this.objectId = checkNotNull(existingObjectId, "existingObjectId cannot be null");

        try {
            this.instanceLeaseRpcClient = createLeaseRpcClient(this.objectId);
            checkNotNull(this.instanceLeaseRpcClient, "LeaseRpcClient cannot be null");

            if (!acquireInitialLease(this.objectId)) {
                throw new InitializationException("Failed to acquire initial lease for object: " + this.objectId);
           }
           leasingActive.set(true); // Mark as active now
            // Schedule renewals and register with PhantomReference
            ScheduledFuture<?> renewalFuture = scheduleLeaseRenewalTask(this.objectId);
            setupPhantomReference(renewalFuture);
        } catch (Exception e) {
            cleanupAfterInitFailure();
            throw new InitializationException("Failed to initialize proxy for existing object " + existingObjectId + ": " + e.getMessage(), e);
        }
    }

    // --- Abstract Method ---
    protected abstract void performRpcSetup() throws Exception;
    protected abstract RefactoredObjectID performRemoteCreateAndGetId(String clientId, Object... args) throws Exception;
    protected abstract void performSubclassRpcCleanup();
    public static AbstractRefactoredClient fromID(RefactoredObjectID existingId){
        return null;
    };

    // --- Factory method for LeaseRpcClient ---
    protected LeaseRpcClient createLeaseRpcClient(RefactoredObjectID targetObjectId) {
        return new GrpcLeaseRpcClient(targetObjectId);
    }

    private boolean acquireInitialLease(RefactoredObjectID idToLease) {
        try {
            return this.instanceLeaseRpcClient.acquireLease(clientId);
        } catch (Exception e) {
            return false;
        }
    }

    // Schedules renewal and RETURNS the future
    private ScheduledFuture<?> scheduleLeaseRenewalTask(RefactoredObjectID idToLease) {
        if (!leasingActive.get()) return null; // Don't schedule if not active
        if (leaseRenewalFrequencyMillis <= 0) { return null;  }

        Runnable renewalRunnable = new Runnable() {
            @Override
            public void run() {
                // Check closed flag first
                if (closed.get()) {
                    return;
                }
                // Check if leasing should still be active
                if (!leasingActive.get()) {
                     return;
                }
                try {
                    boolean success = instanceLeaseRpcClient.renewLease(clientId);
                    if (!success) {
                        leasingActive.set(false);
                    }
                } catch (Exception e) {
                     leasingActive.set(false); // Stop trying on error
                }
            }
        };
        return sharedScheduler.scheduleWithFixedDelay(
                renewalRunnable, leaseRenewalFrequencyMillis, leaseRenewalFrequencyMillis, TimeUnit.MILLISECONDS);
   }

    // --- PhantomReference Setup (Java 8 compatible) ---
    private void setupPhantomReference(ScheduledFuture<?> renewalFuture) {
        this.cleanupState = new CleanupState(
           this.instanceLeaseRpcClient,
           this.clientId,
           renewalFuture,
           this.objectId.getInstanceID());

        // Register with the PhantomReference system
        this.phantomReference = new PhantomReference<>(this, referenceQueue);
        cleanupMap.put(this.phantomReference, this.cleanupState);
   }

    /**
     * Represents the state needed for cleanup and the cleanup action itself.
     * MUST be a static inner class or a separate top-level class.
     * It should NOT hold a direct reference to the AbstractRefactoredClient instance.
     */
    private static class CleanupState implements Runnable {
        private final LeaseRpcClient leaseClientToClean;
        private final String clientIdToRelease;
        private final ScheduledFuture<?> renewalFutureToCancel;
        private final String instanceIdForInfo; // Optional: for context if needed

        // Flag to ensure run() logic executes only once
        private final AtomicBoolean cleaned = new AtomicBoolean(false);

        CleanupState(LeaseRpcClient leaseClient, String clientId, ScheduledFuture<?> renewalFuture, String instanceId) {
            this.leaseClientToClean = leaseClient; // Can be null if init failed before creation
            this.clientIdToRelease = clientId;
            this.renewalFutureToCancel = renewalFuture; // Can be null if scheduling failed/disabled
            this.instanceIdForInfo = instanceId;
        }

        @Override
        public void run() {
            // This method is called either by cleanup thread (GC) or by explicit close
            if (cleaned.compareAndSet(false, true)) {
                // 1. Cancel Future Task
                if (renewalFutureToCancel != null && !renewalFutureToCancel.isDone()) {
                    renewalFutureToCancel.cancel(false);
                }

                // 2. Release Lease (best effort)
                if (leaseClientToClean != null && clientIdToRelease != null) {
                     try {
                         leaseClientToClean.releaseLease(clientIdToRelease);
                     } catch (Exception e) { /* ignore */ }
                }

                // 3. Close Lease Client
                if (leaseClientToClean != null) {
                     try {
                         leaseClientToClean.close(); // Should be idempotent
                     } catch (Exception e) { /* ignore */ }
                }
            }
        }
    }

    // --- Static Cleanup Thread (Java 8 compatible) ---
    private static Thread createCleanupThread() {
        Thread thread = new Thread(new Runnable() {
            @Override
            public void run() {
                while (!Thread.currentThread().isInterrupted()) {
                    try {
                        // Wait for a PhantomReference to be enqueued
                        Reference<? extends AbstractRefactoredClient> ref = referenceQueue.remove();
                        if (ref instanceof PhantomReference) {
                            PhantomReference<AbstractRefactoredClient> phantomRef =
                                (PhantomReference<AbstractRefactoredClient>) ref;

                            // Get the cleanup state and run cleanup
                            CleanupState state = cleanupMap.remove(phantomRef);
                            if (state != null) {
                                state.run();
                            }

                            // Clear the reference
                            phantomRef.clear();
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        break;
                    } catch (Exception e) {
                        // Log error but continue processing
                        System.err.println("Error in cleanup thread: " + e.getMessage());
                    }
                }
            }
        }, "RefactoredClientCleanupThread");

        thread.setDaemon(true);
        thread.start();
        return thread;
    }

    // --- AutoCloseable Method ---
    @Override
    public final void close() {
        if (closed.compareAndSet(false, true)) {
            leasingActive.set(false); // Mark as inactive

            // Explicitly trigger the cleanup action
            if (this.cleanupState != null) {
                this.cleanupState.run(); // Execute cleanup immediately
            }

            // Remove from cleanup map and clear phantom reference
            if (this.phantomReference != null) {
                cleanupMap.remove(this.phantomReference);
                this.phantomReference.clear();
            }

            // Clean up subclass resources AFTER core cleanup
            try { performSubclassRpcCleanup(); } catch (Exception e) { /* Ignore */ }

             // Help GC (optional)
            this.cleanupState = null;
            this.phantomReference = null;
        }
    }

    // --- Cleanup on Init Failure ---
     private void cleanupAfterInitFailure() {
         if (this.instanceLeaseRpcClient != null) {
             try { this.instanceLeaseRpcClient.close(); } catch (Exception e) { /* Ignore */ }
             this.instanceLeaseRpcClient = null;
         }
         try { performSubclassRpcCleanup(); } catch (Exception e) { /* Ignore */ }
    }

    public RefactoredObjectID toID() {
        return this.objectId;
    }

    // --- Helpers ---
    protected final void ensureNotClosed() {
        if(closed.get()) {
            throw new IllegalStateException("Client proxy has been closed for object: " + this.objectId);
        }
    }
    public final RefactoredObjectID getObjectID() { return this.objectId; }

    // --- Static Initializers ---
    private static ScheduledExecutorService createSharedScheduler() {
        // Use anonymous inner class for ThreadFactory
         ThreadFactory threadFactory = new ThreadFactory() {
             private final AtomicInteger threadNumber = new AtomicInteger(1);
             @Override
             public Thread newThread(Runnable r) {
                 Thread t = new Thread(r, "refactoring-client-lease-scheduler-" + threadNumber.getAndIncrement());
                 t.setDaemon(true);
                 return t;
             }
         };
         final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor(threadFactory);

         // Use anonymous inner class for shutdown hook Runnable
          Runtime.getRuntime().addShutdownHook(new Thread(new Runnable() {
              @Override
              public void run() {
                  scheduler.shutdown();
                  try {
                      if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                          scheduler.shutdownNow();
                      }
                  } catch (InterruptedException e) {
                      scheduler.shutdownNow();
                      Thread.currentThread().interrupt();
                  }

                  // Interrupt cleanup thread
                  if (cleanupThread != null && cleanupThread.isAlive()) {
                      cleanupThread.interrupt();
                  }
              }
          }, "LeaseSchedulerShutdownHook"));
          return scheduler;
    }

    private static long loadRenewalFrequency() {
         String freqStr = System.getenv("LEASE_RENEWAL_FREQUENCY_MS");
         long defaultFreq = 20000L;
         if (freqStr == null || freqStr.trim().isEmpty()) { return defaultFreq; }
         try {
             long freq = Long.parseLong(freqStr);
             return freq > 0 ? freq : defaultFreq;
         } catch (NumberFormatException e) { return defaultFreq; }
    }

    // Helper for null checks (Objects.requireNonNull is Java 7+)
    private static <T> T checkNotNull(T obj, String message) {
        if (obj == null) {
            throw new NullPointerException(message);
        }
        return obj;
    }

    // Custom exception
    public static class InitializationException extends RuntimeException {
        private static final long serialVersionUID = 1L;
        public InitializationException(String message) { super(message); }
        public InitializationException(String message, Throwable cause) { super(message, cause); }
    }
}