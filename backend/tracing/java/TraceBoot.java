import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.lang.reflect.Array;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Collection;
import java.util.IdentityHashMap;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Debuggee entry point. Runs inside the traced JVM, ahead of the user's main.
 *
 * System.out goes to an in-memory buffer (OUT) that the tracer reads through
 * JDI at every step, so per-step output is exact (no pipe races). The user's
 * uncaught exception is stored in ERROR and done() is a breakpoint target
 * that tells the tracer the program finished.
 *
 * snapshot() encodes the objects the tracer placed in ROOTS into the trace's
 * heap format. The tracer calls it through JDI once per step: one invocation
 * instead of a debugger round trip per object. It must never run user code
 * (a user breakpoint hit inside an invocation would deadlock the tracer), so
 * user objects are read only through reflection on fields, and only exact
 * java.* classes are read through their own (JDK) iteration methods.
 */
public final class TraceBoot {
    public static final ByteArrayOutputStream OUT = new ByteArrayOutputStream();
    public static String ERROR = null;

    public static final Object[] ROOTS = new Object[512];
    static final int MAX_ITEMS = 64;
    static final int MAX_DEPTH = 12;
    // Holding every encoded object keeps ids stable: one id, one object.
    static final IdentityHashMap<Object, String> IDS = new IdentityHashMap<Object, String>();

    public static void main(String[] args) throws Exception {
        final long limitMs = args.length > 1 ? Long.parseLong(args[1]) : 30000L;
        Thread watchdog = new Thread("trace-watchdog") {
            @Override
            public void run() {
                try {
                    Thread.sleep(limitMs);
                } catch (InterruptedException ignored) {
                    return;
                }
                // Never outlive the tracer. halt() can block while JDWP holds a
                // suspended thread, so SIGKILL ourselves first.
                try {
                    new ProcessBuilder("/bin/sh", "-c", "kill -9 " + ProcessHandle.current().pid()).start();
                    Thread.sleep(2000);
                } catch (Throwable ignored) {
                    // fall through to halt
                }
                Runtime.getRuntime().halt(3);
            }
        };
        watchdog.setDaemon(true);
        watchdog.start();

        System.setOut(new PrintStream(OUT, true, "UTF-8"));
        System.setIn(new ByteArrayInputStream(new byte[0]));
        // Warm the encoder before user code runs, so its classes are loaded.
        ROOTS[0] = new ArrayList<Object>();
        snapshot(1);
        IDS.clear();
        ROOTS[0] = null;
        ClassLoader loader = TraceBoot.class.getClassLoader();
        for (int i = 2; i < args.length; i++) {
            try {
                Class.forName(args[i], false, loader).getDeclaredFields(); // load + link, no init
            } catch (Throwable ignored) {
                // a class that cannot load will fail the same way in user code
            }
        }
        try {
            Class<?> target = Class.forName(args[0]);
            Method main = target.getDeclaredMethod("main", String[].class);
            main.setAccessible(true);
            main.invoke(null, (Object) new String[0]);
        } catch (InvocationTargetException e) {
            ERROR = describe(e.getCause() != null ? e.getCause() : e);
        } catch (Throwable t) {
            ERROR = describe(t);
        }
        System.out.flush();
        done();
        Runtime.getRuntime().halt(0);
    }

    private static String describe(Throwable t) {
        String message = t.getMessage();
        String name = t.getClass().getSimpleName();
        return message == null ? name : name + ": " + message;
    }

    static void done() {
    }

    // ------------------------------------------------------------ snapshot

    /** heap JSON, then "\u0000", then each root's JSON value separated by "\u0001". */
    public static String snapshot(int count) {
        Encoder encoder = new Encoder();
        StringBuilder roots = new StringBuilder();
        for (int i = 0; i < count; i++) {
            if (i > 0) {
                roots.append('\u0001');
            }
            Object value;
            try {
                value = encoder.encode(ROOTS[i], 0);
            } catch (Throwable t) {
                value = "…";
            }
            Json.write(roots, value);
            ROOTS[i] = null;
        }
        StringBuilder out = new StringBuilder();
        Json.write(out, encoder.heap);
        out.append('\u0000').append(roots);
        return out.toString();
    }

    static final class Encoder {
        final Map<String, Object> heap = new LinkedHashMap<String, Object>();

        Object encode(Object v, int depth) {
            if (v == null || v instanceof String || v instanceof Boolean) {
                return v;
            }
            if (v instanceof Integer || v instanceof Long || v instanceof Short || v instanceof Byte) {
                return ((Number) v).longValue();
            }
            if (v instanceof Double || v instanceof Float) {
                return number(((Number) v).doubleValue());
            }
            if (v instanceof Character) {
                return String.valueOf(v);
            }
            Class<?> c = v.getClass();
            if (c == StringBuilder.class || c == StringBuffer.class) {
                return v.toString();
            }
            if (v instanceof Enum) {
                return ((Enum<?>) v).name();
            }
            if (depth > MAX_DEPTH) {
                return "…";
            }
            String id = IDS.get(v);
            if (id == null) {
                id = String.valueOf(IDS.size() + 1);
                IDS.put(v, id);
            }
            if (!heap.containsKey(id)) {
                heap.put(id, new LinkedHashMap<String, Object>()); // reserve so cycles terminate
                heap.put(id, describe(v, c, depth));
            }
            Map<String, Object> ref = new LinkedHashMap<String, Object>();
            ref.put("ref", id);
            return ref;
        }

        Map<String, Object> describe(Object v, Class<?> c, int depth) {
            String name = c.getName();
            boolean jdk = name.startsWith("java.") || name.startsWith("javax.") || name.startsWith("jdk.")
                || name.startsWith("sun.") || name.startsWith("com.sun.");
            if (c.isArray()) {
                int n = Math.min(Array.getLength(v), MAX_ITEMS);
                List<Object> items = new ArrayList<Object>(n);
                for (int i = 0; i < n; i++) {
                    items.add(encode(Array.get(v, i), depth + 1));
                }
                return kind("list", "items", items);
            }
            if (jdk && v instanceof Map) {
                List<Object> entries = new ArrayList<Object>();
                Iterator<?> it = ((Map<?, ?>) v).entrySet().iterator();
                while (it.hasNext() && entries.size() < MAX_ITEMS) {
                    Map.Entry<?, ?> e = (Map.Entry<?, ?>) it.next();
                    List<Object> pair = new ArrayList<Object>(2);
                    pair.add(encode(e.getKey(), depth + 1));
                    pair.add(encode(e.getValue(), depth + 1));
                    entries.add(pair);
                }
                return kind("dict", "entries", entries);
            }
            if (jdk && v instanceof Collection) {
                List<Object> items = new ArrayList<Object>();
                Iterator<?> it = ((Collection<?>) v).iterator();
                while (it.hasNext() && items.size() < MAX_ITEMS) {
                    items.add(encode(it.next(), depth + 1));
                }
                return kind(v instanceof java.util.Set ? "set" : "list", "items", items);
            }
            if (jdk && v instanceof Map.Entry) {
                List<Object> pair = new ArrayList<Object>(2);
                pair.add(encode(((Map.Entry<?, ?>) v).getKey(), depth + 1));
                pair.add(encode(((Map.Entry<?, ?>) v).getValue(), depth + 1));
                return kind("tuple", "items", pair);
            }
            Map<String, Object> obj = new LinkedHashMap<String, Object>();
            obj.put("kind", "object");
            obj.put("class", simpleName(c));
            Map<String, Object> fields = new LinkedHashMap<String, Object>();
            if (!jdk) {
                List<Class<?>> chain = new ArrayList<Class<?>>();
                for (Class<?> k = c; k != null && k != Object.class; k = k.getSuperclass()) {
                    chain.add(0, k);
                }
                for (Class<?> k : chain) {
                    for (Field f : k.getDeclaredFields()) {
                        if (Modifier.isStatic(f.getModifiers()) || f.isSynthetic()) {
                            continue;
                        }
                        // trySetAccessible, not setAccessible: no exception for fields
                        // of JDK superclasses (strong encapsulation); just skip them.
                        if (f.trySetAccessible()) {
                            try {
                                fields.put(f.getName(), encode(f.get(v), depth + 1));
                            } catch (IllegalAccessException ignored) {
                                // unreachable after trySetAccessible
                            }
                        }
                    }
                }
            }
            obj.put("fields", fields);
            return obj;
        }
    }

    static Map<String, Object> kind(String kind, String key, Object value) {
        Map<String, Object> obj = new LinkedHashMap<String, Object>();
        obj.put("kind", kind);
        obj.put(key, value);
        return obj;
    }

    static String simpleName(Class<?> c) {
        String n = c.getName();
        if (n.contains("$$Lambda")) {
            return "lambda";
        }
        int slash = n.indexOf('/');
        if (slash >= 0) {
            n = n.substring(0, slash);
        }
        n = n.substring(n.lastIndexOf('.') + 1);
        return n.substring(n.lastIndexOf('$') + 1);
    }

    static Object number(double d) {
        if (Double.isNaN(d)) {
            return "NaN";
        }
        if (Double.isInfinite(d)) {
            return d > 0 ? "∞" : "-∞";
        }
        return d;
    }

    static final class Json {
        @SuppressWarnings("unchecked")
        static void write(StringBuilder sb, Object v) {
            if (v == null) {
                sb.append("null");
            } else if (v instanceof String) {
                string(sb, (String) v);
            } else if (v instanceof Boolean || v instanceof Long) {
                sb.append(v);
            } else if (v instanceof Double) {
                sb.append(Double.toString((Double) v));
            } else if (v instanceof Map) {
                sb.append('{');
                boolean first = true;
                for (Map.Entry<String, Object> e : ((Map<String, Object>) v).entrySet()) {
                    if (!first) {
                        sb.append(',');
                    }
                    first = false;
                    string(sb, e.getKey());
                    sb.append(':');
                    write(sb, e.getValue());
                }
                sb.append('}');
            } else if (v instanceof List) {
                sb.append('[');
                boolean first = true;
                for (Object item : (List<Object>) v) {
                    if (!first) {
                        sb.append(',');
                    }
                    first = false;
                    write(sb, item);
                }
                sb.append(']');
            } else {
                string(sb, String.valueOf(v));
            }
        }

        static void string(StringBuilder sb, String s) {
            sb.append('"');
            for (int i = 0; i < s.length(); i++) {
                char c = s.charAt(i);
                switch (c) {
                    case '"': sb.append("\\\""); break;
                    case '\\': sb.append("\\\\"); break;
                    case '\n': sb.append("\\n"); break;
                    case '\r': sb.append("\\r"); break;
                    case '\t': sb.append("\\t"); break;
                    default:
                        if (c < 0x20 || (c >= 0xD800 && c <= 0xDFFF) || c == 0x2028 || c == 0x2029) {
                            sb.append(String.format("\\u%04x", (int) c));
                        } else {
                            sb.append(c);
                        }
                }
            }
            sb.append('"');
        }
    }
}
