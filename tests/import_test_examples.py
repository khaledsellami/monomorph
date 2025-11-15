# test_grpc_refactor_client.py (or a separate constants file)

# --- Source Code Snippets ---
SOURCE_OLD_UTIL = """
package com.old;
public class Util { public void doUtil() {} }
"""
SOURCE_OLD_DATA = """
package com.old;
public class Data { public String getInfo() { return "old_data"; } }
"""
SOURCE_OLD_HELPER = """
package com.old;
public class OldHelper { public void help() {} }
"""
SOURCE_OLD_CONFIG = """
package com.old;
public class Config { public static final String KEY = "value"; }
"""
SOURCE_OLD_TARGETCLASS = """
package com.old;
public class TargetClass {}
"""

SOURCE_PROCESSOR_USES_UTIL_DATA = """
package com.app;
import com.old.Util;
import com.old.Data;
import java.util.Map;

public class Processor {
    private Util u = new Util();
    private Data d;
    public void process(Data inputData) {
        this.d = inputData;
        u.doUtil();
        System.out.println(d.getInfo());
    }
    public Map<Util, Data> getMap() { return null; }
}
"""

SOURCE_USER_USES_TARGET_CONFIG = """
package com.app;
import com.old.TargetClass;
import com.old.Config;

public class User {
    private TargetClass target;
    private String configKey = Config.KEY;

    public User(TargetClass t) { this.target = t; }
    public String getConfig() { return configKey; }
}
"""

SOURCE_ADMIN_USES_CONFIG = """
package com.app;
import com.old.Config;

public class Admin {
    public void checkConfig() {
        System.out.println("Admin config: " + Config.KEY);
    }
}
"""

# --- Expected Output Snippets ---
# Expected for refactor_single replacing only Util
EXPECTED_PROCESSOR_SINGLE_UTIL_REPLACED = """
package com.app;

import com.newpkg.Utility;
import com.old.Data;
import java.util.Map;

public class Processor {
    private Utility u = new Utility();
    private Data d;
    public void process(Data inputData) {
        this.d = inputData;
        u.doUtil();
        System.out.println(d.getInfo());
    }
    public Map<Utility, Data> getMap() {
        return null; 
    }
}
"""

# Expected for batch_target replacing Util and Data
EXPECTED_PROCESSOR_BATCH_REPLACED = """
package com.app;

import com.newpkg.Utility;
import java.util.Map;
import org.changed.pkg.Info;

public class Processor {
    private Utility u = new Utility();
    private Info d;
    public void process(Info inputData) {
        this.d = inputData;
        u.doUtil();
        System.out.println(d.getInfo());
    }
    public Map<Utility, Info> getMap() {
        return null;
    }
}
"""

EXPECTED_USER_REPLACED = """
package com.app;

import com.newpkg.Target;
import com.shared.Settings;

public class User {
    private Target target;
    private String configKey = Settings.KEY;

    public User(Target t) {
        this.target = t;
    }
    public String getConfig() {
        return configKey;
    }
}
"""
EXPECTED_ADMIN_REPLACED = """
package com.app;

import com.shared.Settings;

public class Admin {
    public void checkConfig() {
        System.out.println("Admin config: " + Settings.KEY);
    }
}
"""