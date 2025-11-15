{# Jinja2 template for a basic Java gRPC Server #}
{# Variables:
    ms_name:           The name of the microservice.
    package_name:      The Java package for the server class.
    server_class_name: The name of the generated Java server class.
    port:              The default TCP port for the server.
    port_env_var_name: The name of the environment variable to check for the port.
    service_details:   A list of the service implementation classes.
        full_name:     The fully qualified name of a service implementation class.
        simple_name:   The simple name of the service implementation class.
        is_dto:        Whether the service corresponds to a class transformed into a DTO (Data Transfer Object).
    default_lease_duration: The default lease duration in milliseconds.
    lease_duration_env_var_name: The name of the environment variable for lease duration.
#}
package {{ package_name }};

// gRPC imports
import io.grpc.Server;
import io.grpc.ServerBuilder;

// Service implementation imports
{% for service in service_details %}
import {{ service.full_name }};
{% endfor %}

// Leasing imports
import {{ package_name }}.shared.server.LeaseManager;
import {{ package_name }}.shared.server.CaffeineLeaseManager;
import {{ package_name }}.shared.server.LeasingServiceImpl;

// Helper imports
import {{ package_name }}.generated.helpers.IDMapper;

// Java imports
import java.io.IOException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Generated gRPC Server {{ server_class_name }}.
 * Hosts the leasing service and the following services:
 * {% for service in service_details %}
 * - {{ service.simple_name }} ({{ service.full_name }})
 * {% endfor %}
 */
public class {{ server_class_name }} {

    private Server server;
    private final int port;
    private final LeaseManager leaseManager; // Use interface type
    private final ScheduledExecutorService leaseScheduler; // Scheduler instance

    public {{ server_class_name }}(int port) throws Exception {
        this.port = port;
        ServerBuilder<?> serverBuilder = ServerBuilder.forPort(port);

        // 1. Create the Shared Scheduler for Leasing
        this.leaseScheduler = createLeaseScheduler();

        // 2. Create the LeaseManager Implementation
        this.leaseManager = createLeaseManager(this.leaseScheduler);

        // 3. Add the leasing service
        serverBuilder.addService(new LeasingServiceImpl(this.leaseManager));

        // 4. Register all known proxies
        IDMapper.registerProxies();

        // 5. Add service implementations
        {% for service in service_details %}
        {% set simple_name = service.simple_name %}
        // Register the service with the server and the IDMapper
        {% set variable_name = simple_name[0].lower()+simple_name[1:]+"Instance" %}
        {{ simple_name }} {{ variable_name }} = new {{ simple_name }}(this.leaseManager);
        serverBuilder.addService({{ variable_name }});
        // Register the service with the IDMapper
        {% if not service.is_dto %}
        IDMapper.registerServerManager({{ variable_name }});
        {% endif %}
        {% endfor %}

        this.server = serverBuilder.build();
    }

    /**
     * Creates and configures the shared ScheduledExecutorService for the LeaseManager.
     *
     * @return A configured ScheduledExecutorService instance.
     */
    private ScheduledExecutorService createLeaseScheduler() {
        // Use a ThreadFactory for naming and daemon status
        ThreadFactory leaseSchedulerThreadFactory = new ThreadFactory() {
            private final AtomicInteger threadNumber = new AtomicInteger(1);
            private final String namePrefix = "lease-manager-scheduler-";

            @Override
            public Thread newThread(Runnable r) {
                Thread t = new Thread(r, namePrefix + threadNumber.getAndIncrement());
                t.setDaemon(true); // Allow JVM exit even if this thread runs
                return t;
            }
        };
        return Executors.newSingleThreadScheduledExecutor(leaseSchedulerThreadFactory);
    }

    /**
     * Creates a LeaseManager instance.
     * This method should be replaced with the actual implementation.
     * @return A new LeaseManager instance.
     */
    private LeaseManager createLeaseManager(ScheduledExecutorService scheduler) {
        // 1. Determine lease duration from environment or default
        long defaultDuration = {{ default_lease_duration }};
        String durationEnvValue = System.getenv("{{ lease_duration_env_var_name }}");
        long leaseDuration = defaultDuration;

        if (durationEnvValue != null && !durationEnvValue.isEmpty()) {
            try {
                long envDuration = Long.parseLong(durationEnvValue);
                if (envDuration > 0) {
                    leaseDuration = envDuration;
                }
            } catch (NumberFormatException e) {
            }
        }
        // 2. Instantiate the concrete class
        final CaffeineLeaseManager caffeineLeaseManager = new CaffeineLeaseManager(
            leaseDuration,
            leaseScheduler
        );
        return caffeineLeaseManager;
    }

    /**
     * Starts the gRPC server.
     * @throws IOException if unable to bind to the port.
     */
    public void start() throws IOException {
        server.start();
        System.out.println("Microservice '{{ ms_name }}' Server started, listening on " + port);

        // Add a shutdown hook to gracefully terminate the server
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.err.println("*** Shutting down gRPC server since JVM is shutting down");
            try {
                {{ server_class_name }}.this.stop();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt(); // Preserve interrupt status
                System.err.println("*** Server shutdown interrupted: " + e.getMessage());
                e.printStackTrace(System.err);
            }
            System.out.println("*** Server shut down");
        }));
    }

    /**
     * Stops the gRPC server.
     * @throws InterruptedException if server termination is interrupted.
     */
    public void stop() throws InterruptedException {
        // 1. Shutdown Lease Manager
        if (this.leaseManager != null) {
            this.leaseManager.shutdown(); // Call shutdown via interface
        }

        // 2. Shutdown Lease Scheduler
        if (this.leaseScheduler != null && !this.leaseScheduler.isShutdown()) {
            this.leaseScheduler.shutdown();
            try {
                long timeout = 5; TimeUnit units = TimeUnit.SECONDS;
                if (!this.leaseScheduler.awaitTermination(timeout, units)) {
                    this.leaseScheduler.shutdownNow(); // Force shutdown
                     if (!this.leaseScheduler.awaitTermination(timeout, units)) {
                          System.err.println("ERROR: Lease Scheduler did not terminate even after forcing.");
                     }
                }
            } catch (InterruptedException ie) {
                this.leaseScheduler.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }

        // 3. Shutdown gRPC Server
        if (this.server != null && !this.server.isShutdown()) {
            try {
                this.server.shutdown().awaitTermination(30, TimeUnit.SECONDS); // Wait for gRPC calls to finish
            } catch (InterruptedException e) {
                 this.server.shutdownNow(); // Force immediate shutdown if interrupted
                 Thread.currentThread().interrupt();
            }
        }
    }

    /**
     * Await termination on the main thread since the grpc library uses daemon threads.
     * @throws InterruptedException if awaiting termination is interrupted.
     */
    private void blockUntilShutdown() throws InterruptedException {
        if (server != null) {
            server.awaitTermination();
        }
    }

    /**
     * Determines the port to use, checking environment variables first.
     * @return The port number.
     */
    private static int getPort() {
        int defaultPort = {{ port }};
        String portEnvVarName = "{{ port_env_var_name }}";
        String portEnvVarValue = System.getenv(portEnvVarName);

        if (portEnvVarValue != null && !portEnvVarValue.isEmpty()) {
            try {
                int envPort = Integer.parseInt(portEnvVarValue);
                return envPort;
            } catch (NumberFormatException e) {
                System.err.println("WARN: Invalid port value '" + portEnvVarValue + "' in environment variable "
                        + portEnvVarName + ". Falling back to default port " + defaultPort + ".");
                // Fall through to return default port
            }
        } 
        return defaultPort;
    }


    /**
     * Main method to launch the server.
     */
    public static void main(String[] args) throws Exception {
        final int serverPort = getPort();
        final {{ server_class_name }} server = new {{ server_class_name }}(serverPort);

        try {
            server.start();
            server.blockUntilShutdown();
        } catch (IOException | InterruptedException e) {
            System.err.println("ERROR: Server failed to start on port " + serverPort);
            e.printStackTrace(System.err);
            System.exit(1); // Indicate failure
        }
    }
}