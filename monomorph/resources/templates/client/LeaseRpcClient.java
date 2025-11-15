package {{ package_name }}.shared.client;


/** LeaseRpcClient Interface */
public interface LeaseRpcClient extends AutoCloseable {
    boolean acquireLease(String clientId) throws Exception;
    boolean renewLease(String clientId) throws Exception;
    void releaseLease(String clientId) throws Exception;
    // AutoCloseable::close is inherited
}