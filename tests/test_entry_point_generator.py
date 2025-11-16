import unittest

from monomorph.assembly.entrypoint import EntryPointGenerator
from monomorph.helpers import HelperManager


def normalize(code: str) -> str:
    return "\n".join([line.strip() for line in code.strip().splitlines() if line.strip()])


class TestEntryPointGenerator(unittest.TestCase):

    # Test Case 1: Basic generation with a single service
    def test_generate_basic_single_service(self):
        ms_name = "OrderingService"
        package_name = "com.example.ordering"
        generator = EntryPointGenerator(HelperManager(package_name))
        class_name = "OrderingServer"
        services = ["com.example.ordering.impl.OrderServiceImpl"]
        port = 50051 # Default
        env_var_name = "MR_GRPC_PORT" # Default

        generated_code = generator.generate_grpc_entry_point(
            ms_name, package_name, class_name, services, port, env_var_name
        )

        # Basic structural checks
        self.assertIn(f"package {package_name};", generated_code)
        self.assertIn(f"public class {class_name}", generated_code)
        self.assertIn(f"Microservice '{ms_name}' Server started", generated_code)

        # Service checks
        print(generated_code)
        self.assertIn(f"import {services[0]};", generated_code)
        self.assertIn(f"serverBuilder.addService(new OrderServiceImpl(this.leaseManager));", generated_code)
        self.assertIn(f"* - OrderServiceImpl ({services[0]})", generated_code)

        # Port and Env Var checks
        self.assertIn(f"int defaultPort = {port};", generated_code)
        self.assertIn(f'String portEnvVarName = "{env_var_name}";', generated_code)
        self.assertIn("final int serverPort = getPort();", generated_code)

    # Test Case 2: Generation with multiple services and custom port/env var
    def test_generate_multiple_services_custom_config(self):
        ms_name = "UserService"
        package_name = "com.example.users"
        generator = EntryPointGenerator(HelperManager(package_name))
        class_name = "UserManagementServer"
        services = [
            "com.example.users.impl.UserProfileServiceImpl",
            "com.example.users.impl.AuthServiceImpl"
        ]
        port = 9090
        env_var_name = "USER_SERVICE_PORT"

        generated_code = generator.generate_grpc_entry_point(
            ms_name, package_name, class_name, services, port, env_var_name
        )

        # Basic structural checks
        self.assertIn(f"package {package_name};", generated_code)
        self.assertIn(f"public class {class_name}", generated_code)
        self.assertIn(f"Microservice '{ms_name}' Server started", generated_code)

        # Service checks (ensure both are present)
        self.assertIn(f"import {services[0]};", generated_code)
        self.assertIn(f"import {services[1]};", generated_code)
        self.assertIn(f"serverBuilder.addService(new UserProfileServiceImpl(this.leaseManager));", generated_code)
        self.assertIn(f"serverBuilder.addService(new AuthServiceImpl(this.leaseManager));", generated_code)
        self.assertIn(f"* - UserProfileServiceImpl ({services[0]})", generated_code)
        self.assertIn(f"* - AuthServiceImpl ({services[1]})", generated_code)


        # Port and Env Var checks (custom values)
        self.assertIn(f"int defaultPort = {port};", generated_code)
        self.assertIn(f'String portEnvVarName = "{env_var_name}";', generated_code)

    # Test Case 3: Generation with no services (edge case)
    def test_generate_no_services(self):
        ms_name = "GatewayService"
        package_name = "com.example.gateway"
        generator = EntryPointGenerator(HelperManager(package_name))
        class_name = "GatewayServer"
        services = [] # Empty list
        port = 8000
        env_var_name = "GATEWAY_PORT"

        generated_code = generator.generate_grpc_entry_point(
            ms_name, package_name, class_name, services, port, env_var_name
        )

        # Basic structural checks
        self.assertIn(f"package {package_name};", generated_code)
        self.assertIn(f"public class {class_name}", generated_code)
        self.assertIn(f"Microservice '{ms_name}' Server started", generated_code)

        # Service checks (ensure no service imports or additions)
        self.assertEqual(generated_code.count("serverBuilder.addService"), 1) # Only the lease service should be found
        # Check the comment block is minimal
        self.assertIn("Hosts the leasing service and the following services:", generated_code)
        self.assertNotIn("* - ", generated_code) # No bullet points for services

        # Port and Env Var checks (custom values)
        self.assertIn(f"int defaultPort = {port};", generated_code)
        self.assertIn(f'String portEnvVarName = "{env_var_name}";', generated_code)

    # Test Case 4: Exact output comparison for a specific scenario
    def test_generate_exact_output_comparison(self):
        ms_name = "PaymentService"
        package_name = "com.example.payments"
        generator = EntryPointGenerator(HelperManager(package_name))
        class_name = "PaymentServer"
        services = ["com.example.payments.impl.PaymentServiceImpl"]
        port = 60051
        env_var_name = "PAYMENT_PORT"

        expected_output = normalize(test4_expected_output)

        generated_code = generator.generate_grpc_entry_point(
            ms_name, package_name, class_name, services, port, env_var_name
        )
        generated_code = normalize(generated_code)
        # os.makedirs("test_output", exist_ok=True)
        # with open("test_output/test4_generated_output.java", "w") as f:
        #     f.write(generated_code)
        # with open("test_output/test4_expected_output.java", "w") as f:
        #     f.write(expected_output)

        self.assertEqual(expected_output, generated_code)

    # Test Case 5: Exact output comparison for a scenario with multiple services
    def test_generate_exact_output_multi_comparison(self):
        ms_name = "InventoryService"
        package_name = "com.warehouse.inventory"
        generator = EntryPointGenerator(HelperManager(package_name))
        class_name = "InventoryMgmtServer"
        services = [
            "com.warehouse.inventory.impl.StockServiceImpl",
            "com.warehouse.inventory.impl.ReservationServiceImpl"
        ]
        port = 7001
        env_var_name = "INVENTORY_SVC_PORT"

        expected_output = normalize(test5_expected_output)

        generated_code = generator.generate_grpc_entry_point(
            ms_name, package_name, class_name, services, port, env_var_name
        )
        # os.makedirs("test_output", exist_ok=True)
        # with open("test_output/test5_output.java", "w") as f:
        #     f.write(generated_code)
        generated_code = normalize(generated_code)
        # with open("test_output/test5_expected_output.java", "w") as f:
        #     f.write(expected_output)
        # with open("test_output/test5_generated_output.java", "w") as f:
        #     f.write(generated_code)

        self.assertEqual(expected_output, generated_code)

    # Test Case 6: Basic combined entry point generation with external gRPC server
    def test_basic_combined_entry_point(self):
        class_name = "CombinedMainApp"
        package_name = "com.example.ordering"
        generator = EntryPointGenerator(HelperManager(package_name))
        old_main = "com.example.ordering.OrderingApplication"
        grpc_main = "com.example.grpc.OrderingServer"

        generated_code = generator.generate_combined_entry_point(
            class_name, package_name, old_main, grpc_main
        )

        # Basic structural checks
        self.assertIn(f"package {package_name};", generated_code)
        self.assertIn(f"public class {class_name}", generated_code)
        self.assertIn(f"import {old_main};", generated_code)
        self.assertIn(f"import {grpc_main};", generated_code)

        # Check class name and main method
        self.assertIn(f"public static void main(String[] args)", generated_code)
        self.assertIn(f"{class_name} combinedMain = new {class_name}();", generated_code)

        # Check old main and gRPC server integration
        self.assertIn("OrderingApplication.main(oldMainArgs);", generated_code)
        self.assertIn("OrderingServer.main(grpcServerArgs);", generated_code)

        # Check shutdown hook
        self.assertIn(f"{class_name}-ShutdownHook", generated_code)
        self.assertIn("ExecutorService executorService;", generated_code)

    # Test Case 7: Combined entry point with gRPC server in the same package
    def test_combined_entry_point_same_package(self):
        class_name = "CombinedUserApp"
        package_name = "com.example.users"
        generator = EntryPointGenerator(HelperManager(package_name))
        old_main = "com.example.users.UserApplication"
        grpc_main = "com.example.users.UserServer"  # Same package as package_name

        generated_code = generator.generate_combined_entry_point(
            class_name, package_name, old_main, grpc_main
        )

        # Basic structural checks
        self.assertIn(f"package {package_name};", generated_code)
        self.assertIn(f"public class {class_name}", generated_code)
        self.assertIn(f"import {old_main};", generated_code)

        # No import for grpc_main since it's in the same package
        self.assertNotIn(f"import {grpc_main};", generated_code)

        # Check old main and gRPC server integration
        self.assertIn("UserApplication.main(oldMainArgs);", generated_code)
        self.assertIn("UserServer.main(grpcServerArgs);", generated_code)

    # Test Case 8: Combined entry point with differently structured class names
    def test_complex_class_names(self):
        class_name = "AllInOneServer"
        package_name = "org.company.service"
        generator = EntryPointGenerator(HelperManager(package_name))
        old_main = "org.company.legacy.LegacyAppWithLongName"
        grpc_main = "org.company.grpc.servers.GrpcServerWithComplexName"

        generated_code = generator.generate_combined_entry_point(
            class_name, package_name, old_main, grpc_main
        )

        # Basic structural checks
        self.assertIn(f"package {package_name};", generated_code)
        self.assertIn(f"public class {class_name}", generated_code)
        self.assertIn(f"import {old_main};", generated_code)
        self.assertIn(f"import {grpc_main};", generated_code)

        # Check class extraction from FQNs
        self.assertIn("LegacyAppWithLongName.main(oldMainArgs);", generated_code)
        self.assertIn("GrpcServerWithComplexName.main(grpcServerArgs);", generated_code)
        self.assertIn("* LegacyAppWithLongName and GrpcServerWithComplexName", generated_code)

    # Test Case 9: Exact output comparison for a specific scenario
    def test_exact_combined_output(self):
        class_name = "PaymentCombinedApp"
        package_name = "com.example.payments"
        generator = EntryPointGenerator(HelperManager(package_name))
        old_main = "com.example.payments.PaymentApplication"
        grpc_main = "com.example.grpc.PaymentServer"

        expected_output = test9_expected_output

        generated_code = generator.generate_combined_entry_point(
            class_name, package_name, old_main, grpc_main
        )

        self.assertEqual(normalize(expected_output), normalize(generated_code))

    # Test Case 10: Combined entry point with gRPC server in same package (exact output)
    def test_exact_combined_output_same_package(self):
        class_name = "InventoryCombinedApp"
        package_name = "com.warehouse.inventory"
        generator = EntryPointGenerator(HelperManager(package_name))
        old_main = "com.warehouse.inventory.InventoryApplication"
        grpc_main = "com.warehouse.inventory.InventoryServer"  # Same package

        expected_output = test10_expected_output

        generated_code = generator.generate_combined_entry_point(
            class_name, package_name, old_main, grpc_main
        )

        self.assertEqual(normalize(expected_output), normalize(generated_code))


test4_expected_output = """package com.example.payments;

// gRPC imports
import io.grpc.Server;
import io.grpc.ServerBuilder;

// Service implementation imports
import com.example.payments.impl.PaymentServiceImpl;

// Leasing imports
import com.example.payments.shared.server.LeaseManager;
import com.example.payments.shared.server.CaffeineLeaseManager;
import com.example.payments.shared.server.LeasingServiceImpl;

// Java imports
import java.io.IOException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Generated gRPC Server PaymentServer.
 * Hosts the leasing service and the following services:
 * 
 * - PaymentServiceImpl (com.example.payments.impl.PaymentServiceImpl)
 * 
 */
public class PaymentServer {

    private Server server;
    private final int port;
    private final LeaseManager leaseManager; // Use interface type
    private final ScheduledExecutorService leaseScheduler; // Scheduler instance

    public PaymentServer(int port) {
        this.port = port;
        ServerBuilder<?> serverBuilder = ServerBuilder.forPort(port);

        // 1. Create the Shared Scheduler for Leasing
        this.leaseScheduler = createLeaseScheduler();
        
        // 2. Create the LeaseManager Implementation
        this.leaseManager = createLeaseManager(this.leaseScheduler);
        
        // 3. Add the leasing service
        serverBuilder.addService(new LeasingServiceImpl(this.leaseManager));
        
        // 4. Add service implementations

        serverBuilder.addService(new PaymentServiceImpl(this.leaseManager));


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
        long defaultDuration = 60000;
        String durationEnvValue = System.getenv("MM_LEASE_DURATION");
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
        System.out.println("Microservice 'PaymentService' Server started, listening on " + port);

        // Add a shutdown hook to gracefully terminate the server
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.err.println("*** Shutting down gRPC server since JVM is shutting down");
            try {
                PaymentServer.this.stop();
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
        int defaultPort = 60051;
        String portEnvVarName = "PAYMENT_PORT";
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
    public static void main(String[] args) {
        final int serverPort = getPort();
        final PaymentServer server = new PaymentServer(serverPort);

        try {
            server.start();
            server.blockUntilShutdown();
        } catch (IOException e) {
            System.err.println("ERROR: Server failed to start on port " + serverPort);
            e.printStackTrace(System.err);
            System.exit(1); // Indicate failure
        }
    }
}
"""


test5_expected_output = """package com.warehouse.inventory;

// gRPC imports
import io.grpc.Server;
import io.grpc.ServerBuilder;

// Service implementation imports
import com.warehouse.inventory.impl.StockServiceImpl;
import com.warehouse.inventory.impl.ReservationServiceImpl;

// Leasing imports
import com.warehouse.inventory.shared.server.LeaseManager;
import com.warehouse.inventory.shared.server.CaffeineLeaseManager;
import com.warehouse.inventory.shared.server.LeasingServiceImpl;

// Java imports
import java.io.IOException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Generated gRPC Server InventoryMgmtServer.
 * Hosts the leasing service and the following services:
 * 
 * - StockServiceImpl (com.warehouse.inventory.impl.StockServiceImpl)
 * 
 * - ReservationServiceImpl (com.warehouse.inventory.impl.ReservationServiceImpl)
 * 
 */
public class InventoryMgmtServer {

    private Server server;
    private final int port;
    private final LeaseManager leaseManager; // Use interface type
    private final ScheduledExecutorService leaseScheduler; // Scheduler instance

    public InventoryMgmtServer(int port) {
        this.port = port;
        ServerBuilder<?> serverBuilder = ServerBuilder.forPort(port);

        // 1. Create the Shared Scheduler for Leasing
        this.leaseScheduler = createLeaseScheduler();
        
        // 2. Create the LeaseManager Implementation
        this.leaseManager = createLeaseManager(this.leaseScheduler);
        
        // 3. Add the leasing service
        serverBuilder.addService(new LeasingServiceImpl(this.leaseManager));
        
        // 4. Add service implementations

        serverBuilder.addService(new StockServiceImpl(this.leaseManager));
        
        serverBuilder.addService(new ReservationServiceImpl(this.leaseManager));
        

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
        long defaultDuration = 60000;
        String durationEnvValue = System.getenv("MM_LEASE_DURATION");
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
        System.out.println("Microservice 'InventoryService' Server started, listening on " + port);

        // Add a shutdown hook to gracefully terminate the server
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.err.println("*** Shutting down gRPC server since JVM is shutting down");
            try {
                InventoryMgmtServer.this.stop();
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
        int defaultPort = 7001;
        String portEnvVarName = "INVENTORY_SVC_PORT";
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
    public static void main(String[] args) {
        final int serverPort = getPort();
        final InventoryMgmtServer server = new InventoryMgmtServer(serverPort);

        try {
            server.start();
            server.blockUntilShutdown();
        } catch (IOException e) {
            System.err.println("ERROR: Server failed to start on port " + serverPort);
            e.printStackTrace(System.err);
            System.exit(1); // Indicate failure
        }
    }
}
"""

test9_expected_output = """
package com.example.payments;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import com.example.payments.PaymentApplication;
import com.example.grpc.PaymentServer;

/**
 * Generated Main class to concurrently run the main methods of
 * PaymentApplication and PaymentServer within the same JVM.
 *
 * Compatible with Java 7 (uses Anonymous Inner Classes).
 *
 * NOTE: Graceful shutdown relies on the individual main methods handling
 * Thread interruption correctly (e.g., catching InterruptedException,
 * checking Thread.currentThread().isInterrupted()) to perform their own cleanup.
 */
public class PaymentCombinedApp {

    private ExecutorService executorService;

    public static void main(String[] args) {
        PaymentCombinedApp combinedMain = new PaymentCombinedApp();
        combinedMain.start(args);
    }

    /**
     * Starts the execution of both main methods concurrently.
     * @param args Command line arguments passed to this PaymentCombinedApp.
     *             These are currently *not* passed down to the individual mains,
     *             but could be split and passed if necessary.
     */
    public void start(String[] args) {

        // Use a fixed thread pool with 2 threads.
        executorService = Executors.newFixedThreadPool(2);

        // Register a shutdown hook
        Runtime.getRuntime().addShutdownHook(new Thread(new Runnable() {
            @Override
            public void run() {
                // Call the stop method of the enclosing instance
                stop();
            }
        }, "PaymentCombinedApp-ShutdownHook")); 


        // --- Arguments for the target mains ---
        final String[] oldMainArgs = new String[0];
        final String[] grpcServerArgs = new String[0];

        // Submit OldMain using an Anonymous Inner Class
        executorService.submit(new Runnable() {
            @Override
            public void run() {
                try {
                    PaymentApplication.main(oldMainArgs);
                } catch (Throwable t) { 
                    // Consider adding logic here to potentially stop the other task or the whole application
                    // stop(); 
                }
            }
        });

         // Submit NewGrpcServer using an Anonymous Inner Class
        executorService.submit(new Runnable() {
            @Override
            public void run() {
                try {
                    PaymentServer.main(grpcServerArgs);
                } catch (Throwable t) { // Catch Throwable to capture Errors as well
                     // Consider adding logic here to potentially stop the other task or the whole application
                     // stop(); // Uncomment to shutdown everything if one part fails critically
                }
            }
        });

        // The main thread of PaymentCombinedApp can exit now.
        // The application stays alive due to the non-daemon threads in the ExecutorService.
    }

    /**
     * Initiates the shutdown sequence for the executor service.
     * This will attempt to interrupt the threads running the main methods.
     */
    public void stop() {
        // Use a temporary variable for thread-safety check
        ExecutorService exec = executorService;
        if (exec != null && !exec.isShutdown()) {

            // Use shutdownNow() to interrupt the threads running the main methods.
            exec.shutdownNow();

            try {
                // Wait a bit for tasks to terminate after interruption.
                !exec.awaitTermination(5, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                // Force shutdown again if interrupted during waiting
                exec.shutdownNow();
                // Preserve interrupt status
                Thread.currentThread().interrupt();
            }
        }
    }
}
"""


test10_expected_output = """
package com.warehouse.inventory;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import com.warehouse.inventory.InventoryApplication;

/**
 * Generated Main class to concurrently run the main methods of
 * InventoryApplication and InventoryServer within the same JVM.
 *
 * Compatible with Java 7 (uses Anonymous Inner Classes).
 *
 * NOTE: Graceful shutdown relies on the individual main methods handling
 * Thread interruption correctly (e.g., catching InterruptedException,
 * checking Thread.currentThread().isInterrupted()) to perform their own cleanup.
 */
public class InventoryCombinedApp {

    private ExecutorService executorService;

    public static void main(String[] args) {
        InventoryCombinedApp combinedMain = new InventoryCombinedApp();
        combinedMain.start(args);
    }

    /**
     * Starts the execution of both main methods concurrently.
     * @param args Command line arguments passed to this InventoryCombinedApp.
     *             These are currently *not* passed down to the individual mains,
     *             but could be split and passed if necessary.
     */
    public void start(String[] args) {

        // Use a fixed thread pool with 2 threads.
        executorService = Executors.newFixedThreadPool(2);

        // Register a shutdown hook
        Runtime.getRuntime().addShutdownHook(new Thread(new Runnable() {
            @Override
            public void run() {
                // Call the stop method of the enclosing instance
                stop();
            }
        }, "InventoryCombinedApp-ShutdownHook")); 


        // --- Arguments for the target mains ---
        final String[] oldMainArgs = new String[0];
        final String[] grpcServerArgs = new String[0];

        // Submit OldMain using an Anonymous Inner Class
        executorService.submit(new Runnable() {
            @Override
            public void run() {
                try {
                    InventoryApplication.main(oldMainArgs);
                } catch (Throwable t) { 
                    // Consider adding logic here to potentially stop the other task or the whole application
                    // stop(); 
                }
            }
        });

         // Submit NewGrpcServer using an Anonymous Inner Class
        executorService.submit(new Runnable() {
            @Override
            public void run() {
                try {
                    InventoryServer.main(grpcServerArgs);
                } catch (Throwable t) { // Catch Throwable to capture Errors as well
                     // Consider adding logic here to potentially stop the other task or the whole application
                     // stop(); // Uncomment to shutdown everything if one part fails critically
                }
            }
        });

        // The main thread of InventoryCombinedApp can exit now.
        // The application stays alive due to the non-daemon threads in the ExecutorService.
    }

    /**
     * Initiates the shutdown sequence for the executor service.
     * This will attempt to interrupt the threads running the main methods.
     */
    public void stop() {
        // Use a temporary variable for thread-safety check
        ExecutorService exec = executorService;
        if (exec != null && !exec.isShutdown()) {

            // Use shutdownNow() to interrupt the threads running the main methods.
            exec.shutdownNow();

            try {
                // Wait a bit for tasks to terminate after interruption.
                !exec.awaitTermination(5, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                // Force shutdown again if interrupted during waiting
                exec.shutdownNow();
                // Preserve interrupt status
                Thread.currentThread().interrupt();
            }
        }
    }
}
"""