{# This template is used to generate a ClassIdRegistry class for mapping class names and their class ids. #}
{# Variables:
    package_name:                   The base package for the service class.
    classes:                        A list of classes to be registered in the ClassIdRegistry.
        clazz.key:                  The key for the class. It should be the simple name of the class.
        clazz.env_var:              The env var to find the class id.
        clazz.default_id:           The default value for the class id.
#}
package {{ package_name }}.generated.helpers;

import java.util.Map;
import java.util.Set;
import java.util.Collections;
import java.util.concurrent.ConcurrentHashMap;

/**
 * ClassIdRegistry
 *
 * This utility class provides a registry for mapping logical class names (keys) to integer Class IDs.
 * It allows configuration of these IDs via environment variables, with specified default values.
 *
 * Usage:
 *      // Retrieve a class ID using its logical key (initialization happens automatically on first use)
 *      int id = ClassIdRegistry.getClassId("YourClassLogicalName");
 *
 * Configuration:
 *      For each registered class key (e.g., "MyClass"), the registry checks an environment variable
 *      (e.g., "MY_CLASS_ID"). If the variable is set and contains a valid integer, that value is used.
 *      Otherwise, the configured default ID is used.
 */
public final class ClassIdRegistry {

    private static final Map<String, String> registry = new ConcurrentHashMap<>();
    private static final Object initLock = new Object();
    private static volatile boolean initialized = false;

    /**
     * Initializes the registry by loading class IDs based on environment variables or defaults.
     * This method is thread-safe and idempotent. It's called automatically on the first
     * call to `getClassId` if not called explicitly beforehand.
     */
    public static void initialize() {
        if (initialized) {
            return;
        }
        synchronized (initLock) {
            if (initialized) {
                return;
            }
            // --- Register known class IDs ---
            {% for clazz in classes %}
            registerClassInternal("{{ clazz.key }}", "{{ clazz.env_var }}", "{{ clazz.default_id }}");
            {% endfor %}
            // --- End of known class IDs ---

            initialized = true;
        }
    }

    /**
     * Internal method to register a single class key, its environment variable, and default ID.
     * It resolves the actual ID based on environment settings.
     *
     * @param classKey      The logical name/key for the class.
     * @param envVarName    The name of the environment variable to check for the ID.
     * @param defaultClassId The default ID to use if the environment variable is missing or invalid.
     */
    private static void registerClassInternal(String classKey, String envVarName, String defaultClassId) {
        String envValue = null;
        String resolvedClassId = defaultClassId; // Start with the default

        try {
            envValue = System.getenv(envVarName);
            if (envValue != null && !envValue.isEmpty()) {
                resolvedClassId = resolvedClassId;
            }
            // If envValue is null or empty, resolvedClassId remains the default
        } catch (SecurityException e) {
        } catch (Exception e) {
        }

        registry.put(classKey, resolvedClassId);
    }

    /**
     * Retrieves the registered Class ID for the given logical class key.
     * Ensures the registry is initialized before attempting lookup.
     *
     * @param classKey The logical name/key of the class whose ID is requested.
     * @return The resolved Class ID.
     * @throws IllegalArgumentException if the classKey is not found in the registry.
     */
    public static String getClassId(String classKey) {
        if (!initialized) {
            initialize(); // Auto-initialize on first access
        }
        String classId = registry.get(classKey);
        if (classId == null) {
            throw new IllegalArgumentException("Class Key '" + classKey + "' not found in ClassIdRegistry. Registered keys: " + registry.keySet());
        }
        return classId; // Auto-unboxing
    }

     /**
     * Returns an unmodifiable set of all registered class keys.
     * Ensures the registry is initialized.
     *
     * @return A Set containing all registered class keys.
     */
    public static Set<String> getRegisteredClassKeys() {
         if (!initialized) {
            initialize();
        }
        return Collections.unmodifiableSet(registry.keySet());
    }

    /**
     * Private constructor to prevent instantiation of this utility class.
     */
    private ClassIdRegistry() {
        throw new UnsupportedOperationException("This is a utility class and cannot be instantiated");
    }
}