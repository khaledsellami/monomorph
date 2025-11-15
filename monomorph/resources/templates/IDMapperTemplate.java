{# This template is used to generate the IDMapper class for mapping class ids to servers or proxies. #}
{# Variables:
    package_name:                   The base package for the service class.
    proxies:                        A list of classes to be registered in the ClassIdRegistry.
        proxy.full_name:            The fqn of the proxy class.
        clazz.name:                 The simple name of the proxy class.
#}
package {{ package_name }}.generated.helpers;

import {{ package_name }}.shared.RefactoredObjectID;
import {{ package_name }}.shared.client.AbstractRefactoredClient;
import {{ package_name }}.shared.server.ServerObjectManager; // The server manager interface
import {{ package_name }}.generated.helpers.ClassIdRegistry;

// Import proxies
{% for proxy in proxies %}
import {{ proxy.full_name }};
{% endfor %}

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class IDMapper {

    // Registry for Server Object Managers, keyed by the Class ID they manage
    private static final Map<String, ServerObjectManager> serverManagers = new ConcurrentHashMap<>();

    // Registry for Client Proxy Classes, keyed by the Class ID they represent
    private static final Map<String, Class<? extends AbstractRefactoredClient>> clientClasses = new ConcurrentHashMap<>();

    private IDMapper() { throw new IllegalStateException("Utility class"); }

    // --- Registration Methods ---

    /**
     * Registers a server-side component responsible for managing instances of a specific class type.
     * @param manager The ServerObjectManager instance.
     */
    public static void registerServerManager(ServerObjectManager manager) throws Exception {
        if (manager == null) {
            throw new IllegalArgumentException("ServerObjectManager cannot be null");
        }
        String classId = manager.getManagedClassId();
        if (classId == null || classId.trim().isEmpty()) {
            throw new IllegalArgumentException("ServerObjectManager must provide a valid managed classId");
        }
        serverManagers.put(classId, manager);
    }

     /**
     * Registers a client proxy class.
     * @param clientClass The Class object of the client proxy (must extend AbstractRefactoredClient).
     */
    public static void registerClientProxy(Class<? extends AbstractRefactoredClient> clientClass) throws Exception {
        String representsClassId = ClassIdRegistry.getClassId(clientClass.getClass().getSimpleName());
        if (clientClass == null) {
            throw new IllegalArgumentException("clientClass cannot be null");
        }
         if (!AbstractRefactoredClient.class.isAssignableFrom(clientClass)) {
             throw new IllegalArgumentException("clientClass " + clientClass.getName() + " must extend AbstractRefactoredClient");
         }
         // Verify the required static fromID method exists
         try {
             Method fromIdMethod = clientClass.getMethod("fromID", RefactoredObjectID.class);
             if (!Modifier.isStatic(fromIdMethod.getModifiers()) || !Modifier.isPublic(fromIdMethod.getModifiers())) {
                 throw new IllegalArgumentException("Class " + clientClass.getName() + " must have a 'public static fromID(RefactoredObjectID id)' method.");
             }
             if (!AbstractRefactoredClient.class.isAssignableFrom(fromIdMethod.getReturnType())) {
                  throw new IllegalArgumentException("Method 'fromID' in " + clientClass.getName() + " must return a type assignable to AbstractRefactoredClient.");
             }
         } catch (NoSuchMethodException e) {
             throw new IllegalArgumentException("Class " + clientClass.getName() + " must have a 'public static fromID(RefactoredObjectID id)' method.", e);
         }
        clientClasses.put(representsClassId, clientClass);
    }

    // --- Core Mapping Methods ---

    /**
     * Converts an object (Client Proxy or Actual Server-Side Object) to its RefactoredObjectID.
     */
    public static RefactoredObjectID toID(Object object) throws Exception {
        if (object == null) {
            throw new IllegalArgumentException("Input object cannot be null");
        }

        // 1. Check if it's a Client Proxy
        if (object instanceof AbstractRefactoredClient) {
            return ((AbstractRefactoredClient) object).toID(); 
        }

        // 2. Assume it's an Actual Server-Side Object
        // Using the name of the class to get the Class ID from the ClassIdRegistry
        String classId = ClassIdRegistry.getClassId(object.getClass().getName());

        ServerObjectManager manager = serverManagers.get(classId);

        if (manager != null) {
            try {
                // The manager's toID implementation should handle the actual instance type check implicitly via LeaseManager
                return manager.toID(object);
            } catch (ClassCastException e) {
                 // This might occur if registration is incorrect, but less likely if toID relies on LeaseManager lookup
                 throw new IllegalArgumentException("Type mismatch: Registered manager for ClassID " + manager.getManagedClassId()
                     + " encountered incompatible object type " + object.getClass().getName(), e);
            } catch (Exception e) {
                 // Catch exceptions from the manager's toID implementation (e.g., IllegalArgumentException if not found)
                 throw new RuntimeException("Error during server manager toID execution for ClassID " + manager.getManagedClassId() + ": " + e.getMessage(), e);
            }
        } else {
            throw new IllegalArgumentException("No registered ServerObjectManager found for object type: "
                + object.getClass().getName() + " (ClassID: " + classId + ")");
        }
    }

    /**
     * Converts a RefactoredObjectID back to its corresponding object representation
     * (Client Proxy or Actual Server-Side Object).
     */
    public static Object fromID(RefactoredObjectID id) throws Exception {
        if (id == null) {
            throw new IllegalArgumentException("Input RefactoredObjectID cannot be null");
        }
        if (id.getClassID() == null || id.getClassID().trim().isEmpty()) {
            throw new IllegalArgumentException("RefactoredObjectID must have a non-empty classID");
        }

        String classId = id.getClassID();

        // 1. Check Server Managers
        if (serverManagers.containsKey(classId)) {
            ServerObjectManager manager = serverManagers.get(classId);
            try {
                // Delegate to the manager's fromID method
                return manager.fromID(id);
            } catch (Exception e) {
                // Catch exceptions from the manager's fromID implementation
                throw new RuntimeException("Error during server manager fromID execution for ID " + id + ": " + e.getMessage(), e);
            }
        }

        // 2. Check Client Proxy Classes
        if (clientClasses.containsKey(classId)) {
            Class<? extends AbstractRefactoredClient> clientClass = clientClasses.get(classId);
            try {
                Method fromIdMethod = clientClass.getMethod("fromID", RefactoredObjectID.class);
                Object proxy = fromIdMethod.invoke(null, id); // invoke static method
                return proxy;
            } catch (NoSuchMethodException e) {
                throw new RuntimeException("Internal error: Registered client class " + clientClass.getName() + " missing static fromID(RefactoredObjectID) method.", e);
            } catch (IllegalAccessException e) {
                throw new RuntimeException("Internal error: Cannot access static fromID method in " + clientClass.getName(), e);
            } catch (InvocationTargetException e) {
                // Unwrap the exception thrown by the fromID method itself
                throw new RuntimeException("Exception occurred during client proxy creation via fromID for " + clientClass.getName() + ": " + e.getCause().getMessage(), e.getCause());
            } catch(ClassCastException e){
                 throw new RuntimeException("Internal error: Static fromID method in " + clientClass.getName() + " did not return an AbstractRefactoredClient.", e);
            }
        }

        // 3. ID doesn't map to anything known
        throw new IllegalArgumentException("No registered ServerObjectManager or ClientProxy found for ClassID: " + classId);
    }

    /**
     * Registers all known proxies (currently defined directly).
     * This method is called during application startup to ensure all components are registered.
     */
    public static void registerProxies() {
        {% for proxy in proxies %}
        registerClientProxy({{ proxy.name }}.class);
        {% endfor %}
    }
    
    public static void clearRegistries() {
        serverManagers.clear();
        clientClasses.clear();
    }
}